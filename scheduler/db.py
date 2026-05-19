"""Database layer — SQLite locally / Postgres in production.

One ``DATABASE_URL`` selects the backend (set it to a Postgres URL on the
host; unset → local SQLite file). The rest of the package keeps writing
plain ``?``-placeholder SQL: this module translates it and runs it through
SQLAlchemy so the same queries work on both engines.

Schema is versioned in a portable ``schema_meta`` table and migrated
idempotently on connect.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError  # noqa: F401  (re-exported)
from sqlalchemy.pool import NullPool

# Local SQLite fallback when DATABASE_URL is unset. SCHEDULER_DB_PATH lets a
# host point this at a writable disk; tests pass their own path.
DEFAULT_DB_PATH = Path(
    os.environ.get(
        "SCHEDULER_DB_PATH",
        Path(__file__).resolve().parent.parent / "data" / "scheduler.db",
    )
)

SCHEMA_VERSION = 3

# Per-dialect migration statements (each a list of single statements).
_MIGRATIONS: list[dict[str, list[str]]] = [
    # --- v1: initial schema ------------------------------------------------
    {
        "sqlite": [
            """CREATE TABLE IF NOT EXISTS person (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                is_active  INTEGER NOT NULL DEFAULT 1
                           CHECK (is_active IN (0, 1)),
                created_at TEXT    NOT NULL
            )""",
            """CREATE UNIQUE INDEX IF NOT EXISTS ux_person_active_name
                ON person(name) WHERE is_active = 1""",
            """CREATE TABLE IF NOT EXISTS schedule_entry (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id        INTEGER NOT NULL REFERENCES person(id),
                work_date        TEXT    NOT NULL,
                entry_type       TEXT    NOT NULL
                                 CHECK (entry_type IN ('SHIFT','PTO','UTO')),
                start_time       TEXT,
                end_time         TEXT,
                crosses_midnight INTEGER NOT NULL DEFAULT 0
                                 CHECK (crosses_midnight IN (0, 1)),
                note             TEXT,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL,
                CHECK (
                    (entry_type = 'SHIFT'
                         AND start_time IS NOT NULL AND end_time IS NOT NULL)
                    OR (entry_type IN ('PTO','UTO')
                         AND start_time IS NULL AND end_time IS NULL)
                )
            )""",
            """CREATE INDEX IF NOT EXISTS ix_entry_person_date
                ON schedule_entry(person_id, work_date)""",
            """CREATE INDEX IF NOT EXISTS ix_entry_date
                ON schedule_entry(work_date)""",
        ],
        "postgresql": [
            """CREATE TABLE IF NOT EXISTS person (
                id         BIGSERIAL PRIMARY KEY,
                name       TEXT     NOT NULL,
                is_active  SMALLINT NOT NULL DEFAULT 1
                           CHECK (is_active IN (0, 1)),
                created_at TEXT     NOT NULL
            )""",
            """CREATE UNIQUE INDEX IF NOT EXISTS ux_person_active_name
                ON person(name) WHERE is_active = 1""",
            """CREATE TABLE IF NOT EXISTS schedule_entry (
                id               BIGSERIAL PRIMARY KEY,
                person_id        BIGINT  NOT NULL REFERENCES person(id),
                work_date        TEXT    NOT NULL,
                entry_type       TEXT    NOT NULL
                                 CHECK (entry_type IN ('SHIFT','PTO','UTO')),
                start_time       TEXT,
                end_time         TEXT,
                crosses_midnight SMALLINT NOT NULL DEFAULT 0
                                 CHECK (crosses_midnight IN (0, 1)),
                note             TEXT,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL,
                CHECK (
                    (entry_type = 'SHIFT'
                         AND start_time IS NOT NULL AND end_time IS NOT NULL)
                    OR (entry_type IN ('PTO','UTO')
                         AND start_time IS NULL AND end_time IS NULL)
                )
            )""",
            """CREATE INDEX IF NOT EXISTS ix_entry_person_date
                ON schedule_entry(person_id, work_date)""",
            """CREATE INDEX IF NOT EXISTS ix_entry_date
                ON schedule_entry(work_date)""",
        ],
    },
    # --- v2: case-insensitive active-name uniqueness -----------------------
    {
        "sqlite": [
            "DROP INDEX IF EXISTS ux_person_active_name",
            """CREATE UNIQUE INDEX ux_person_active_name
                ON person(name COLLATE NOCASE) WHERE is_active = 1""",
        ],
        "postgresql": [
            "DROP INDEX IF EXISTS ux_person_active_name",
            """CREATE UNIQUE INDEX ux_person_active_name
                ON person(lower(name)) WHERE is_active = 1""",
        ],
    },
    # --- v3: add the RD (Rest Day) entry type ------------------------------
    # CHECK can't be altered in place, so rebuild schedule_entry. The times
    # rule is generalized to "SHIFT has times, anything else doesn't".
    {
        "sqlite": [
            "ALTER TABLE schedule_entry RENAME TO schedule_entry_old",
            """CREATE TABLE schedule_entry (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id        INTEGER NOT NULL REFERENCES person(id),
                work_date        TEXT    NOT NULL,
                entry_type       TEXT    NOT NULL
                                 CHECK (entry_type IN
                                        ('SHIFT','PTO','UTO','RD')),
                start_time       TEXT,
                end_time         TEXT,
                crosses_midnight INTEGER NOT NULL DEFAULT 0
                                 CHECK (crosses_midnight IN (0, 1)),
                note             TEXT,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL,
                CHECK (
                    (entry_type = 'SHIFT'
                         AND start_time IS NOT NULL AND end_time IS NOT NULL)
                    OR (entry_type <> 'SHIFT'
                         AND start_time IS NULL AND end_time IS NULL)
                )
            )""",
            """INSERT INTO schedule_entry (id, person_id, work_date,
                   entry_type, start_time, end_time, crosses_midnight,
                   note, created_at, updated_at)
               SELECT id, person_id, work_date, entry_type, start_time,
                   end_time, crosses_midnight, note, created_at, updated_at
               FROM schedule_entry_old""",
            "DROP TABLE schedule_entry_old",
            """CREATE INDEX IF NOT EXISTS ix_entry_person_date
                ON schedule_entry(person_id, work_date)""",
            """CREATE INDEX IF NOT EXISTS ix_entry_date
                ON schedule_entry(work_date)""",
        ],
        "postgresql": [
            "ALTER TABLE schedule_entry RENAME TO schedule_entry_old",
            """CREATE TABLE schedule_entry (
                id               BIGSERIAL PRIMARY KEY,
                person_id        BIGINT  NOT NULL REFERENCES person(id),
                work_date        TEXT    NOT NULL,
                entry_type       TEXT    NOT NULL
                                 CHECK (entry_type IN
                                        ('SHIFT','PTO','UTO','RD')),
                start_time       TEXT,
                end_time         TEXT,
                crosses_midnight SMALLINT NOT NULL DEFAULT 0
                                 CHECK (crosses_midnight IN (0, 1)),
                note             TEXT,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL,
                CHECK (
                    (entry_type = 'SHIFT'
                         AND start_time IS NOT NULL AND end_time IS NOT NULL)
                    OR (entry_type <> 'SHIFT'
                         AND start_time IS NULL AND end_time IS NULL)
                )
            )""",
            """INSERT INTO schedule_entry (id, person_id, work_date,
                   entry_type, start_time, end_time, crosses_midnight,
                   note, created_at, updated_at)
               SELECT id, person_id, work_date, entry_type, start_time,
                   end_time, crosses_midnight, note, created_at, updated_at
               FROM schedule_entry_old""",
            "DROP TABLE schedule_entry_old",
            """SELECT setval(
                   pg_get_serial_sequence('schedule_entry','id'),
                   COALESCE((SELECT MAX(id) FROM schedule_entry), 0) + 1,
                   false)""",
            """CREATE INDEX IF NOT EXISTS ix_entry_person_date
                ON schedule_entry(person_id, work_date)""",
            """CREATE INDEX IF NOT EXISTS ix_entry_date
                ON schedule_entry(work_date)""",
        ],
    },
]

_engines: dict[str, Engine] = {}
_engines_lock = threading.Lock()


def _resolve_url(db_path: str | Path | None) -> str:
    if db_path is not None:  # explicit SQLite path (tests / local override)
        return f"sqlite:///{Path(db_path).as_posix()}"
    env = os.environ.get("DATABASE_URL")
    if env:
        # Hosted Postgres URLs come as postgres:// or postgresql://;
        # SQLAlchemy needs the psycopg driver named explicitly.
        if env.startswith("postgres://"):
            env = "postgresql+psycopg://" + env[len("postgres://"):]
        elif env.startswith("postgresql://"):
            env = "postgresql+psycopg://" + env[len("postgresql://"):]
        return env
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"


def _get_engine(url: str) -> Engine:
    with _engines_lock:
        eng = _engines.get(url)
        if eng is None:
            # NullPool: a fresh DBAPI connection per use and closed on
            # release — matches the connect-per-interaction design and
            # frees SQLite file handles promptly (Windows/tests).
            eng = create_engine(url, poolclass=NullPool, future=True)
            if eng.dialect.name == "sqlite":
                @event.listens_for(eng, "connect")
                def _fk_on(dbapi_conn, _rec):  # enforce FKs on SQLite
                    cur = dbapi_conn.cursor()
                    cur.execute("PRAGMA foreign_keys=ON")
                    cur.close()
            _engines[url] = eng
    return eng


def _qmark_to_named(sql: str, params):
    """Translate ``?``-placeholder SQL + a sequence into named binds.

    None of our SQL contains a literal ``?`` inside a quoted string, so a
    straight positional substitution is safe and keeps every call site's
    plain ``?`` SQL working across dialects.
    """
    if params is None:
        return text(sql), {}
    if isinstance(params, dict):
        return text(sql), params
    out, i = [], 0
    for ch in sql:
        if ch == "?":
            out.append(f":p{i}")
            i += 1
        else:
            out.append(ch)
    return text("".join(out)), {f"p{n}": v for n, v in enumerate(params)}


class _Conn:
    """Minimal connection facade: ``.execute/.commit/.rollback/.close``.

    ``execute`` returns a result whose rows support ``row["col"]``,
    ``row.keys()`` and ``"col" in row`` (SQLAlchemy ``RowMapping``).
    """

    def __init__(self, engine: Engine):
        self._raw = engine.connect()

    def execute(self, sql: str, params=None):
        stmt, bound = _qmark_to_named(sql, params)
        return _Result(self._raw.execute(stmt, bound))

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


class _Result:
    def __init__(self, result):
        self._r = result
        self.rowcount = result.rowcount if result.returns_rows is False else -1

    def fetchone(self):
        row = self._r.fetchone()
        return None if row is None else row._mapping

    def fetchall(self):
        return [r._mapping for r in self._r.fetchall()]


Connection = _Conn  # public alias for type hints across the package


def connect(db_path: str | Path | None = None) -> _Conn:
    """Open a connection and run pending migrations.

    Resolution: explicit ``db_path`` (SQLite) → ``DATABASE_URL`` (Postgres
    in prod) → local SQLite file. Callers use a short-lived connection per
    operation (ARCHITECTURE.md).
    """
    conn = _Conn(_get_engine(_resolve_url(db_path)))
    _migrate(conn)
    return conn


def schema_version(conn: _Conn) -> int:
    row = conn.execute("SELECT version FROM schema_meta").fetchone()
    return row["version"] if row else 0


def _migrate(conn: _Conn) -> None:
    dialect = conn._raw.engine.dialect.name
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)"
    )
    conn.commit()
    current = schema_version(conn)
    if current == 0 and conn.execute(
        "SELECT 1 FROM schema_meta"
    ).fetchone() is None:
        conn.execute("INSERT INTO schema_meta (version) VALUES (0)")
        conn.commit()

    if current >= len(_MIGRATIONS):
        return
    for version in range(current, len(_MIGRATIONS)):
        for stmt in _MIGRATIONS[version][dialect]:
            conn.execute(stmt)
        conn.execute("UPDATE schema_meta SET version = ?", (version + 1,))
        conn.commit()
