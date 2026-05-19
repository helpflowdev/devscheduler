"""Scaffold tests for schema + migration."""

from __future__ import annotations

import pytest

from scheduler.db import (
    SCHEMA_VERSION,
    IntegrityError,
    connect,
    schema_version,
)


def test_migration_sets_version(db):
    assert schema_version(db) == SCHEMA_VERSION


def test_core_tables_exist(db):
    # Portable existence check: a trivial SELECT against each table.
    db.execute("SELECT 1 FROM person").fetchall()
    db.execute("SELECT 1 FROM schedule_entry").fetchall()


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "x.db"
    connect(path).close()  # first run
    conn = connect(path)  # second run must not error or duplicate
    assert schema_version(conn) == SCHEMA_VERSION
    conn.close()


def test_active_name_uniqueness_enforced(db):
    db.execute(
        "INSERT INTO person(name, is_active, created_at) VALUES (?, 1, ?)",
        ("Alice", "2026-01-01T00:00:00Z"),
    )
    with pytest.raises(IntegrityError):
        db.execute(
            "INSERT INTO person(name, is_active, created_at) VALUES (?, 1, ?)",
            ("Alice", "2026-01-02T00:00:00Z"),
        )


def test_shift_requires_times_check(db):
    db.execute(
        "INSERT INTO person(name, is_active, created_at) "
        "VALUES ('Bob', 1, 'x')"
    )
    pid = db.execute("SELECT id FROM person").fetchone()["id"]
    with pytest.raises(IntegrityError):  # SHIFT needs both times (CHECK)
        db.execute(
            "INSERT INTO schedule_entry"
            "(person_id, work_date, entry_type, created_at, updated_at) "
            "VALUES (?, '2026-05-18', 'SHIFT', 'x', 'x')",
            (pid,),
        )


def test_multiple_entries_per_date_allowed(db):
    """No DB uniqueness on (person_id, work_date) — PRD §11.4."""
    db.execute(
        "INSERT INTO person(name, is_active, created_at) "
        "VALUES ('Cara', 1, 'x')"
    )
    pid = db.execute("SELECT id FROM person").fetchone()["id"]
    for start, end in (("09:00", "12:00"), ("13:00", "17:00")):
        db.execute(
            "INSERT INTO schedule_entry"
            "(person_id, work_date, entry_type, start_time, end_time,"
            " created_at, updated_at) "
            "VALUES (?, '2026-05-18', 'SHIFT', ?, ?, 'x', 'x')",
            (pid, start, end),
        )
    n = db.execute(
        "SELECT COUNT(*) AS c FROM schedule_entry"
    ).fetchone()["c"]
    assert n == 2
