"""Week math and weekday-preserving roll-forward.

The week starts Monday (PRD §11.1). ``copy_week`` is an exact copy (FR-5);
``copy_week_with_offset`` slides every shift (FR-6).
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


def shift_shift_times(
    start: str, end: str, offset_min: int
) -> tuple[str, str, bool]:
    """Slide a shift by ``offset_min`` (may be negative). Wraps at midnight.

    Returns ``(new_start, new_end, crosses_midnight)``. Duration is
    preserved; ``crosses_midnight`` is recomputed from the new clock times.
    """
    new_start = _to_hhmm(_to_min(start) + offset_min)
    new_end = _to_hhmm(_to_min(end) + offset_min)
    return new_start, new_end, _to_min(new_end) <= _to_min(new_start)


def _copy_core(
    conn: Connection,
    src_any_date: str | date,
    dst_any_date: str | date,
    overwrite: bool,
    offset_min: int | None,
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
            start, end, crosses = r["start_time"], r["end_time"], \
                r["crosses_midnight"]
            if offset_min is not None and r["entry_type"] == "SHIFT":
                start, end, c = shift_shift_times(start, end, offset_min)
                crosses = int(c)
            insert_entry(
                conn,
                person_id=r["person_id"],
                work_date=iso(dst_mon + timedelta(days=shift_days)),
                entry_type=r["entry_type"],
                start_time=start, end_time=end,
                crosses_midnight=crosses, note=r["note"], now=now,
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
    return _copy_core(conn, src_any_date, dst_any_date, overwrite, None)


def copy_week_with_offset(
    conn: Connection,
    src_any_date: str | date,
    dst_any_date: str | date,
    offset_min: int,
    *,
    overwrite: bool = False,
) -> CopyResult:
    """Copy forward with every SHIFT slid by ``offset_min`` (FR-6).

    PTO/UTO copy unchanged; only shifts move. ``crosses_midnight`` is
    recomputed. Same weekday-preserving, single-transaction, overwrite
    semantics as :func:`copy_week`.
    """
    if offset_min == 0:
        raise ValidationError("Offset is zero — use an exact copy instead.")
    return _copy_core(conn, src_any_date, dst_any_date, overwrite, offset_min)


@dataclass(slots=True)
class PreviewRow:
    person_name: str
    dst_date: str
    entry_type: str
    old: str  # "HH:MM–HH:MM" or "" for PTO/UTO
    new: str  # shifted, or "" for PTO/UTO


def preview_offset(
    conn: Connection,
    src_any_date: str | date,
    dst_any_date: str | date,
    offset_min: int,
) -> list[PreviewRow]:
    """Read-only: what :func:`copy_week_with_offset` would write (US-5)."""
    src_mon = monday_of(src_any_date)
    dst_mon = monday_of(dst_any_date)
    src_dates = [iso(d) for d in week_dates(src_mon)]
    rows = conn.execute(
        "SELECT e.*, p.name AS person_name FROM schedule_entry e "
        "JOIN person p ON p.id = e.person_id "
        f"WHERE e.work_date IN ({in_placeholders(7)}) "
        "ORDER BY p.name COLLATE NOCASE, e.work_date",
        src_dates,
    ).fetchall()

    out: list[PreviewRow] = []
    for r in rows:
        shift_days = (date.fromisoformat(r["work_date"]) - src_mon).days
        new_date = iso(dst_mon + timedelta(days=shift_days))
        if r["entry_type"] != "SHIFT":
            out.append(PreviewRow(r["person_name"], new_date,
                                   r["entry_type"], "", ""))
            continue
        s, e, _ = shift_shift_times(
            r["start_time"], r["end_time"], offset_min
        )
        out.append(PreviewRow(
            r["person_name"], new_date, "SHIFT",
            f'{r["start_time"]}–{r["end_time"]}', f"{s}–{e}",
        ))
    return out
