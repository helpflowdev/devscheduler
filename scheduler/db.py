"""SQLite connection + idempotent schema migration.

Single source of truth for the schema. Migrations are tracked with the
SQLite ``PRAGMA user_version`` and applied on every connection (idempotent),
so app startup just calls :func:`connect`.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# DB location. In production set SCHEDULER_DB_PATH to a path on the mounted
# persistent disk (e.g. /var/scheduler-data/scheduler.db). Locally it falls
# back to ./data/scheduler.db (gitignored). Tests pass their own path.
DEFAULT_DB_PATH = Path(
    os.environ.get(
        "SCHEDULER_DB_PATH",
        Path(__file__).resolve().parent.parent / "data" / "scheduler.db",
    )
)

SCHEMA_VERSION = 2

# Ordered migration statements. Index i is applied when user_version <= i.
_MIGRATIONS: list[str] = [
    # --- v1: initial schema -------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS person (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT    NOT NULL
    );

    -- Unique name only among ACTIVE people; deactivated names may be reused.
    CREATE UNIQUE INDEX IF NOT EXISTS ux_person_active_name
        ON person(name) WHERE is_active = 1;

    CREATE TABLE IF NOT EXISTS schedule_entry (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id        INTEGER NOT NULL REFERENCES person(id),
        work_date        TEXT    NOT NULL,                       -- YYYY-MM-DD
        entry_type       TEXT    NOT NULL
                         CHECK (entry_type IN ('SHIFT', 'PTO', 'UTO')),
        start_time       TEXT,                                   -- HH:MM Pacific
        end_time         TEXT,                                   -- HH:MM Pacific
        crosses_midnight INTEGER NOT NULL DEFAULT 0
                         CHECK (crosses_midnight IN (0, 1)),
        note             TEXT,
        created_at       TEXT    NOT NULL,
        updated_at       TEXT    NOT NULL,
        -- SHIFT must have both times; PTO/UTO must have neither.
        CHECK (
            (entry_type = 'SHIFT'
                 AND start_time IS NOT NULL AND end_time IS NOT NULL)
            OR
            (entry_type IN ('PTO', 'UTO')
                 AND start_time IS NULL AND end_time IS NULL)
        )
    );

    -- NOTE: deliberately NO UNIQUE(person_id, work_date). v1 enforces
    -- one-entry-per-date in app logic; schema stays open for multiple
    -- shifts/day later (PRD §11.4).
    CREATE INDEX IF NOT EXISTS ix_entry_person_date
        ON schedule_entry(person_id, work_date);
    CREATE INDEX IF NOT EXISTS ix_entry_date
        ON schedule_entry(work_date);
    """,
    # --- v2: make the active-name uniqueness case-insensitive ---------------
    # So "Dana" and "dana" can't both be active. Enforced in the DB instead
    # of an app pre-check (which was racy).
    """
    DROP INDEX IF EXISTS ux_person_active_name;
    CREATE UNIQUE INDEX ux_person_active_name
        ON person(name COLLATE NOCASE) WHERE is_active = 1;
    """,
]


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection, enforce FKs, and run pending migrations.

    Pass ``":memory:"`` or a temp path in tests. Callers should use a
    short-lived connection per operation (no global connection held across
    Streamlit reruns — see ARCHITECTURE.md).
    """
    target = db_path if db_path is not None else DEFAULT_DB_PATH
    if target != ":memory:":
        parent = Path(target).parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version;").fetchone()[0]
    if current >= len(_MIGRATIONS):
        return  # already current — no commit on every connection
    for version in range(current, len(_MIGRATIONS)):
        conn.executescript(_MIGRATIONS[version])
        conn.execute(f"PRAGMA user_version = {version + 1};")
    conn.commit()
