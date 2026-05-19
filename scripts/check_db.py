"""Verify the configured database works — run this after setting DATABASE_URL.

    python scripts/check_db.py

Connects using the same resolution as the app (DATABASE_URL → Postgres,
else local SQLite), runs the schema migration, and does a round-trip
insert/select that is **rolled back** (no data written). Prints the
backend and schema version. Exit code 0 = good to deploy.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler.db import connect, schema_version  # noqa: E402
from scheduler.util import now_iso  # noqa: E402


def main() -> None:
    conn = connect()
    backend = conn._raw.engine.dialect.name
    print(f"Backend: {backend}")
    print(f"Schema version: {schema_version(conn)}")

    # Non-destructive round trip: insert then roll back.
    conn.execute(
        "INSERT INTO person(name, is_active, created_at) VALUES (?, 1, ?)",
        ("__connectivity_check__", now_iso()),
    )
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM person WHERE name = ?",
        ("__connectivity_check__",),
    ).fetchone()["c"]
    conn.rollback()
    assert n == 1, "insert/select round trip failed"

    still = conn.execute(
        "SELECT COUNT(*) AS c FROM person WHERE name = ?",
        ("__connectivity_check__",),
    ).fetchone()["c"]
    conn.close()
    assert still == 0, "rollback did not take effect"

    print("Round trip OK (rolled back, nothing written).")
    print("Database is ready.")


if __name__ == "__main__":
    main()
