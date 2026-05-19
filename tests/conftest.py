"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from scheduler.db import Connection, connect


@pytest.fixture()
def db(tmp_path) -> Iterator[Connection]:
    """A fresh migrated SQLite DB on a temp file, closed after the test."""
    conn = connect(tmp_path / "test.db")
    try:
        yield conn
    finally:
        conn.close()
