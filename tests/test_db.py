"""Scaffold tests for schema + migration (M0)."""

from __future__ import annotations

import sqlite3

import pytest

from scheduler.db import SCHEMA_VERSION, connect


def test_migration_sets_user_version(db):
    assert db.execute("PRAGMA user_version;").fetchone()[0] == SCHEMA_VERSION


def test_core_tables_exist(db):
    names = {
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
    }
    assert {"person", "schedule_entry"} <= names


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "x.db"
    connect(path).close()  # first run
    conn = connect(path)  # second run must not error or duplicate
    assert conn.execute("PRAGMA user_version;").fetchone()[0] == SCHEMA_VERSION
    conn.close()


def test_active_name_uniqueness_enforced(db):
    db.execute(
        "INSERT INTO person(name, is_active, created_at) VALUES (?, 1, ?)",
        ("Alice", "2026-01-01T00:00:00Z"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO person(name, is_active, created_at) VALUES (?, 1, ?)",
            ("Alice", "2026-01-02T00:00:00Z"),
        )


def test_shift_requires_times_check(db):
    db.execute(
        "INSERT INTO person(name, is_active, created_at) VALUES ('Bob', 1, 'x')"
    )
    pid = db.execute("SELECT id FROM person").fetchone()[0]
    # SHIFT without times violates the CHECK constraint.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO schedule_entry"
            "(person_id, work_date, entry_type, created_at, updated_at) "
            "VALUES (?, '2026-05-18', 'SHIFT', 'x', 'x')",
            (pid,),
        )


def test_multiple_entries_per_date_allowed(db):
    """No DB uniqueness on (person_id, work_date) — PRD §11.4."""
    db.execute(
        "INSERT INTO person(name, is_active, created_at) VALUES ('Cara', 1, 'x')"
    )
    pid = db.execute("SELECT id FROM person").fetchone()[0]
    for start, end in (("09:00", "12:00"), ("13:00", "17:00")):
        db.execute(
            "INSERT INTO schedule_entry"
            "(person_id, work_date, entry_type, start_time, end_time,"
            " created_at, updated_at) "
            "VALUES (?, '2026-05-18', 'SHIFT', ?, ?, 'x', 'x')",
            (pid, start, end),
        )
    assert db.execute("SELECT COUNT(*) FROM schedule_entry").fetchone()[0] == 2
