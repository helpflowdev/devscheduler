"""Small shared helpers used across the scheduler package."""

from __future__ import annotations

from datetime import datetime, timezone


def now_iso() -> str:
    """Current UTC time as an ISO-8601 ``...Z`` string (for created/updated)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def in_placeholders(n: int) -> str:
    """``"?,?,?"`` for an ``IN (...)`` clause of length ``n``."""
    return ",".join("?" * n)
