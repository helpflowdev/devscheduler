"""Planned (advance-filed) PTO/UTO — a forward-looking leave registry.

People file leave weeks ahead. Storing that directly in ``schedule_entry``
doesn't survive a week roll-forward: copy-forward (``weeks.copy_week``) and
template-apply (``templates.apply_template``) both overwrite the destination
week and would wipe a pre-filed leave. So planned leaves live in their own
durable table and are *overlaid* onto a week whenever it is built.

Overlay = for each ``(person, date)`` a leave covers, delete+insert a
PTO/UTO entry, so the leave wins over any shift the build placed there
(the same overwrite semantics used everywhere in v1). The registry is the
source of truth for future leaves and can be re-applied any number of times.
"""

from __future__ import annotations

from datetime import date, timedelta

from scheduler.db import Connection
from scheduler.entries import insert_entry
from scheduler.errors import NotFoundError, ValidationError
from scheduler.models import EntryType, PlannedLeave
from scheduler.util import now_iso
from scheduler.weeks import iso, monday_of, week_dates

_LEAVE_TYPES = (EntryType.PTO, EntryType.UTO)

_SELECT = (
    "SELECT pl.*, p.name AS person_name FROM planned_leave pl "
    "JOIN person p ON p.id = pl.person_id"
)


def _as_iso(value) -> str:
    return value if isinstance(value, str) else value.isoformat()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def add_planned_leave(
    conn: Connection,
    *,
    person_id: int,
    start_date,
    end_date,
    leave_type: EntryType,
    note: str | None = None,
) -> PlannedLeave:
    """Register an advance leave over ``start_date``..``end_date`` inclusive.

    Raises :class:`ValidationError` for a non-PTO/UTO type or an end before
    the start, and :class:`NotFoundError` for an unknown person.
    """
    if leave_type not in _LEAVE_TYPES:
        raise ValidationError("Planned leave must be PTO or UTO.")
    start, end = _as_iso(start_date), _as_iso(end_date)
    if end < start:
        raise ValidationError("End date can't be before the start date.")
    if conn.execute(
        "SELECT 1 FROM person WHERE id = ?", (person_id,)
    ).fetchone() is None:
        raise NotFoundError(f"No person with id {person_id}.")

    new_id = conn.execute(
        "INSERT INTO planned_leave"
        "(person_id, start_date, end_date, leave_type, note, created_at) "
        "VALUES (?,?,?,?,?,?) RETURNING id",
        (person_id, start, end, leave_type.value, note, now_iso()),
    ).fetchone()["id"]
    conn.commit()
    return get_planned_leave(conn, new_id)


def get_planned_leave(conn: Connection, leave_id: int) -> PlannedLeave:
    row = conn.execute(
        f"{_SELECT} WHERE pl.id = ?", (leave_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"No planned leave with id {leave_id}.")
    return PlannedLeave.from_row(row)


def list_planned_leaves(
    conn: Connection, *, since=None
) -> list[PlannedLeave]:
    """Planned leaves, ordered by start date then person name.

    With ``since`` (a date/ISO string) only leaves ending on or after it are
    returned, hiding fully-past ones; without it, everything.
    """
    sql = _SELECT
    params: list = []
    if since is not None:
        sql += " WHERE pl.end_date >= ?"
        params.append(_as_iso(since))
    sql += " ORDER BY pl.start_date, lower(p.name)"
    return [PlannedLeave.from_row(r) for r in conn.execute(sql, params).fetchall()]


def delete_planned_leave(conn: Connection, leave_id: int) -> int:
    """Remove a leave from the registry. Returns rows deleted (0 or 1).

    Already-materialized ``schedule_entry`` rows are left as-is; deleting
    only stops the leave from being re-applied on future builds.
    """
    cur = conn.execute("DELETE FROM planned_leave WHERE id = ?", (leave_id,))
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# Overlay onto a week
# ---------------------------------------------------------------------------
def leaves_overlapping(
    conn: Connection, dates: list[str]
) -> list[PlannedLeave]:
    """Planned leaves whose span intersects ``dates`` (any date list)."""
    if not dates:
        return []
    lo, hi = min(dates), max(dates)
    rows = conn.execute(
        f"{_SELECT} WHERE pl.start_date <= ? AND pl.end_date >= ? "
        "ORDER BY pl.start_date, lower(p.name)",
        (hi, lo),
    ).fetchall()
    return [PlannedLeave.from_row(r) for r in rows]


def overlay_leaves(conn: Connection, dates: list[str], *, now: str) -> int:
    """Overlay every planned leave onto the ``(person, date)`` cells it
    covers within ``dates``. Delete+insert per cell (leave wins over any
    shift). **No commit** — the caller owns the transaction so this can join
    a copy-forward's single transaction. Returns leave-days written.
    """
    if not dates:
        return 0
    date_set = set(dates)
    written = 0
    for lv in leaves_overlapping(conn, dates):
        d = date.fromisoformat(lv.start_date)
        end = date.fromisoformat(lv.end_date)
        while d <= end:
            iso_d = d.isoformat()
            if iso_d in date_set:
                conn.execute(
                    "DELETE FROM schedule_entry "
                    "WHERE person_id = ? AND work_date = ?",
                    (lv.person_id, iso_d),
                )
                insert_entry(
                    conn, person_id=lv.person_id, work_date=iso_d,
                    entry_type=lv.leave_type.value, start_time=None,
                    end_time=None, crosses_midnight=0, note=lv.note, now=now,
                )
                written += 1
            d += timedelta(days=1)
    return written


def apply_planned_leaves_to_week(conn: Connection, any_date_in_week) -> int:
    """Overlay planned leaves onto the week containing ``any_date_in_week``,
    committed as its own transaction.

    Use to pull leaves into a week that's already built without re-copying
    it. Returns the number of leave-days written.
    """
    dates = [iso(d) for d in week_dates(monday_of(any_date_in_week))]
    now = now_iso()
    try:
        written = overlay_leaves(conn, dates, now=now)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return written
