"""Week math and weekday-preserving roll-forward.

The week starts Monday (PRD §11.1). ``copy_week`` copies a week's entries
into the next week, unchanged (FR-5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from scheduler.config import DAY_NAMES  # noqa: F401  (re-exported)
from scheduler.db import Connection
from scheduler.errors import OverwriteRequiredError, ValidationError
from scheduler.util import in_placeholders, now_iso


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def monday_of(value: str | date) -> date:
    """The Monday on or before ``value`` (the week anchor)."""
    d = _as_date(value)
    return d - timedelta(days=d.weekday())  # Monday.weekday() == 0


def week_dates(value: str | date) -> list[date]:
    """The 7 dates Mon..Sun for the week containing ``value``."""
    start = monday_of(value)
    return [start + timedelta(days=i) for i in range(7)]


def add_weeks(value: str | date, n: int) -> date:
    """``value``'s week anchor shifted by ``n`` weeks (Monday returned)."""
    return monday_of(value) + timedelta(weeks=n)


def iso(d: date) -> str:
    return d.isoformat()


@dataclass(slots=True)
class CopyResult:
    copied: int  # entries written into the destination week
    overwritten: int  # destination entries removed first


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    minutes %= 24 * 60  # wrap within the day
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def end_from_duration(start: str, dur_min: int) -> tuple[str, bool]:
    """Given a start ``HH:MM`` and a duration in minutes, return
    ``(end_hhmm, crosses_midnight)``.

    The duration model: pick when it starts and how long it runs; the end
    (and whether it spills past midnight) is derived — no error-prone
    end-time entry.
    """
    if dur_min <= 0:
        raise ValidationError("Duration must be greater than zero.")
    if dur_min >= 24 * 60:
        raise ValidationError("A shift must be shorter than 24 hours.")
    total = _to_min(start) + dur_min
    return _to_hhmm(total), total >= 24 * 60


def duration_minutes(start: str, end: str, crosses_midnight: bool) -> int:
    """Inverse of :func:`end_from_duration` — length of an existing shift,
    used to pre-fill the duration when editing."""
    span = _to_min(end) - _to_min(start)
    if crosses_midnight or span <= 0:
        span += 24 * 60
    return span


def _copy_core(
    conn: Connection,
    src_any_date: str | date,
    dst_any_date: str | date,
    overwrite: bool,
) -> CopyResult:
    from scheduler.entries import find_conflicts, insert_entry  # avoid cycle

    src_mon = monday_of(src_any_date)
    dst_mon = monday_of(dst_any_date)
    if src_mon == dst_mon:
        raise ValidationError("Source and destination weeks are the same.")

    src_dates = [iso(d) for d in week_dates(src_mon)]
    dst_dates = [iso(d) for d in week_dates(dst_mon)]

    src_rows = conn.execute(
        f"SELECT * FROM schedule_entry "
        f"WHERE work_date IN ({in_placeholders(7)}) ORDER BY work_date",
        src_dates,
    ).fetchall()
    if not src_rows:
        raise ValidationError("The source week has no entries to copy.")

    conflicts = find_conflicts(conn, dst_dates)
    if conflicts and not overwrite:
        raise OverwriteRequiredError(conflicts)

    now = now_iso()
    overwritten = 0
    try:
        if overwrite:
            cur = conn.execute(
                f"DELETE FROM schedule_entry "
                f"WHERE work_date IN ({in_placeholders(7)})",
                dst_dates,
            )
            overwritten = cur.rowcount
        for r in src_rows:
            shift_days = (date.fromisoformat(r["work_date"]) - src_mon).days
            insert_entry(
                conn,
                person_id=r["person_id"],
                work_date=iso(dst_mon + timedelta(days=shift_days)),
                entry_type=r["entry_type"],
                start_time=r["start_time"], end_time=r["end_time"],
                crosses_midnight=r["crosses_midnight"],
                note=r["note"], now=now,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return CopyResult(copied=len(src_rows), overwritten=overwritten)


def copy_week(
    conn: Connection,
    src_any_date: str | date,
    dst_any_date: str | date,
    *,
    overwrite: bool = False,
) -> CopyResult:
    """Exact copy of the source week into the destination week (FR-5).

    Weekday-preserving (Mon→Mon, …), single transaction. Existing
    destination entries raise :class:`OverwriteRequiredError` unless
    ``overwrite`` clears the destination week first (PRD §9).
    """
    return _copy_core(conn, src_any_date, dst_any_date, overwrite)
