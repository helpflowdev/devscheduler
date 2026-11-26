"""Week math and weekday-preserving roll-forward.

The week starts Monday (PRD §11.1). ``copy_week`` carries a week's regular
pattern into another week (FR-5, as amended by FR-13): one-off exceptions —
OT, PTO, UTO — are not carried, and a day left empty by dropping them is
refilled from the person's standing schedule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from scheduler.config import DAY_NAMES  # noqa: F401  (re-exported)
from scheduler.db import Connection
from scheduler.errors import OverwriteRequiredError, ValidationError
from scheduler.models import EntryType
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
    copied: int  # source entries carried into the destination week
    overwritten: int  # destination entries removed first
    leaves_applied: int = 0  # planned-leave days overlaid onto the copy
    skipped: int = 0  # source OT/PTO/UTO entries not carried
    filled: int = 0  # days refilled from the standing schedule
    # Days that were skipped-only with no standing day to fall back on, so
    # they're left empty: (person name, "YYYY-MM-DD") in the destination.
    unfilled: list[tuple[str, str]] = field(default_factory=list)


def is_carried(entry_type: str, is_ot: bool) -> bool:
    """Does copy-forward carry this entry? Regular shifts and RD are the
    standing pattern; OT, PTO and UTO are one-off exceptions (FR-13)."""
    return not is_ot and entry_type not in ("PTO", "UTO")


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
    template,
) -> CopyResult:
    # Local imports break the weeks↔entries / weeks↔leaves /
    # weeks↔templates module cycles.
    from scheduler.entries import (
        find_conflicts,
        insert_entry,
        validate_shift_times,
    )
    from scheduler.leaves import overlay_leaves
    from scheduler.templates import DEFAULT_TEMPLATE, standing_day

    if template is None:
        template = DEFAULT_TEMPLATE

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

    # Split the source into what carries and the cells that lose everything
    # (a PTO/UTO day, or an OT-only rest day) — those get the standing day.
    carried = [r for r in src_rows
               if is_carried(r["entry_type"], bool(r["is_ot"]))]
    kept_cells = {(r["person_id"], r["work_date"]) for r in carried}
    emptied = sorted({(r["person_id"], r["work_date"]) for r in src_rows}
                     - kept_cells)
    names: dict[int, str] = {}
    if emptied:
        pids = sorted({pid for pid, _ in emptied})
        names = {r["id"]: r["name"] for r in conn.execute(
            f"SELECT id, name FROM person "
            f"WHERE id IN ({in_placeholders(len(pids))})", pids,
        ).fetchall()}

    def dst_iso(src_iso: str) -> str:
        return iso(dst_mon + (date.fromisoformat(src_iso) - src_mon))

    now = now_iso()
    overwritten = 0
    leaves_applied = 0
    filled = 0
    unfilled: list[tuple[str, str]] = []
    try:
        if overwrite:
            cur = conn.execute(
                f"DELETE FROM schedule_entry "
                f"WHERE work_date IN ({in_placeholders(7)})",
                dst_dates,
            )
            overwritten = cur.rowcount
        for r in carried:
            insert_entry(
                conn,
                person_id=r["person_id"],
                work_date=dst_iso(r["work_date"]),
                entry_type=r["entry_type"],
                start_time=r["start_time"], end_time=r["end_time"],
                crosses_midnight=r["crosses_midnight"],
                note=r["note"], now=now,
            )
        for pid, src_iso in emptied:
            name = names.get(pid, f"#{pid}")
            weekday = date.fromisoformat(src_iso).weekday()
            rows = standing_day(name, weekday, template)
            if not rows:
                unfilled.append((name, dst_iso(src_iso)))
                continue
            for etype, start, end in rows:
                crosses = (validate_shift_times(start, end)
                           if etype is EntryType.SHIFT else False)
                insert_entry(
                    conn, person_id=pid, work_date=dst_iso(src_iso),
                    entry_type=etype.value, start_time=start, end_time=end,
                    crosses_midnight=int(crosses), note=None, now=now,
                )
            filled += 1
        # Advance-filed leaves win over the copied shift on their dates.
        leaves_applied = overlay_leaves(conn, dst_dates, now=now)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return CopyResult(
        copied=len(carried),
        overwritten=overwritten,
        leaves_applied=leaves_applied,
        skipped=len(src_rows) - len(carried),
        filled=filled,
        unfilled=unfilled,
    )


def copy_week(
    conn: Connection,
    src_any_date: str | date,
    dst_any_date: str | date,
    *,
    overwrite: bool = False,
    template=None,
) -> CopyResult:
    """Carry the source week's regular pattern into the destination week
    (FR-5, amended by FR-13).

    Weekday-preserving (Mon→Mon, …), single transaction. Regular shifts and
    RD copy as-is; OT, PTO and UTO are one-offs and are **not** carried.
    A day that held only those is refilled from the person's standing day
    in ``template`` (default: :data:`scheduler.templates.DEFAULT_TEMPLATE`)
    or left empty and reported in ``unfilled``. Planned leaves are then
    overlaid, so next week's real PTO/UTO comes from the leave registry.
    Existing destination entries raise :class:`OverwriteRequiredError`
    unless ``overwrite`` clears the destination week first (PRD §9).
    """
    return _copy_core(conn, src_any_date, dst_any_date, overwrite, template)


def clear_week(conn: Connection, any_date_in_week) -> int:
    """Delete every entry (all people) in that week. Returns rows removed."""
    dates = [iso(d) for d in week_dates(monday_of(any_date_in_week))]
    try:
        cur = conn.execute(
            f"DELETE FROM schedule_entry "
            f"WHERE work_date IN ({in_placeholders(7)})",
            dates,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return cur.rowcount
