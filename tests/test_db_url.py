"""URL resolution for the dual SQLite/Postgres backend."""

from __future__ import annotations

from scheduler.db import _resolve_url


def test_explicit_path_is_sqlite(tmp_path):
    url = _resolve_url(tmp_path / "x.db")
    assert url.startswith("sqlite:///") and url.endswith("x.db")


def test_postgres_scheme_normalized(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/db")
    assert _resolve_url(None) == "postgresql+psycopg://u:p@h:5432/db"


def test_postgresql_scheme_normalized(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    assert _resolve_url(None) == "postgresql+psycopg://u:p@h/db"


def test_already_qualified_url_untouched(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u@h/db")
    assert _resolve_url(None) == "postgresql+psycopg://u@h/db"


def test_default_falls_back_to_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _resolve_url(None).startswith("sqlite:///")
