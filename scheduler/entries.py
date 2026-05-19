"""Schedule entry reads, validation, and bulk apply.

Viewer row policy (PRD §11.3): show every active person, plus any inactive
person who still has an entry in the displayed week, so historical weeks
stay intact after someone is deactivated.
"""

from __future__ import annotations

from dataclasses import dataclass

from scheduler.db import Connection
from scheduler.errors import (
    NotFoundError,
    OverwriteRequiredError,
    ValidationError,
)
from scheduler.models import Entry, EntryType, Person
from scheduler.util import in_placeholders, now_iso
from scheduler.weeks import iso, week_dates

_INSERT_SQL = (
    "INSERT INTO schedule_entry"
    "(person_id, work_date, entry_type, start_time, end_time,"
    " crosses_midnight, note, created_at, updated_at) "
    "VALUES (?,?,?,?,?,?,?,?,?)"
)


def insert_entry(
    conn: Connection,
    *,
    person_id: int,
    work_date: str,
    entry_type: str,
    start_time: str | None,
    end_time: str | None,
    crosses_midnight: int,
    note: str | None,
    now: str,
) -> None:
    """Single place that knows the schedule_entry column list."""
    conn.execute(_INSERT_SQL, (
        person_id, work_date, entry_type, start_time, end_time,
        crosses_midnight, note, now, now,
    ))


def get_week_entries(conn: Connection, any_date: str) -> list[Entry]:
    """All entries whose ``work_date`` falls in ``any_date``'s week."""
    dates = [iso(d) for d in week_dates(any_date)]
    rows = conn.execute(
        f"SELECT * FROM schedule_entry "
        f"WHERE work_date IN ({in_placeholders(len(dates))}) "
        "ORDER BY work_date, start_time",
        dates,
    ).fetchall()
    return [Entry.from_row(r) for r in rows]


def get_week_people(
    conn: Connection,
    any_date: str,
    *,
    entries: list[Entry] | None = None,
) -> list[Person]:
    """Active people ∪ inactive-with-entries-this-week, name-sorted.

    Pass ``entries`` (already loaded for the same week) to skip the
    correlated re-scan of schedule_entry.
    """
    if entries is not None:
        with_entries = {e.person_id for e in entries}
        rows = conn.execute(
            "SELECT id, name, is_active, created_at FROM person "
            "WHERE is_active = 1 ORDER BY name COLLATE NOCASE"
        ).fetchall()
        people = [Person.from_row(r) for r in rows]
        seen = {p.id for p in people}
        extra_ids = with_entries - seen
        if extra_ids:
            rows = conn.execute(
                "SELECT id, name, is_active, created_at FROM person "
                f"WHERE id IN ({in_placeholders(len(extra_ids))})",
                list(extra_ids),
            ).fetchall()
            people += [Person.from_row(r) for r in rows]
            people.sort(key=lambda p: p.name.lower())
        return people

    dates = [iso(d) for d in week_dates(any_date)]
    rows = conn.execute(
        "SELECT id, name, is_active, created_at FROM person "
        "WHERE is_active = 1 "
        "   OR id IN (SELECT DISTINCT person_id FROM schedule_entry "
        f"             WHERE work_date IN ({in_placeholders(len(dates))})) "
        "ORDER BY name COLLATE NOCASE",
        dates,
    ).fetchall()
    return [Person.from_row(r) for r in rows]


@dataclass(slots=True)
class ApplyResult:
    created: int
    overwritten: int  # entries removed and replaced


def _parse_hhmm(value: str, field: str) -> int:
    """`HH:MM` → minutes since midnight. Raises ValidationError."""
    try:
        hh, mm = value.split(":")
        h, m = int(hh), int(mm)
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError
    except (ValueError, AttributeError):
        raise ValidationError(f"{field} must be HH:MM (00:00–23:59).") from None
    return h * 60 + m


def validate_shift_times(start: str, end: str) -> bool:
    """Validate a shift; return ``crosses_midnight``.

    ``end == start`` is a zero-length shift → rejected. ``end < start``
    means the shift crosses midnight (allowed, flagged — PRD §9).
    """
    s = _parse_hhmm(start, "Start time")
    e = _parse_hhmm(end, "End time")
    if s == e:
        raise ValidationError("End time must differ from start time.")
    return e < s


def find_conflicts(
    conn: Connection,
    dates: list[str],
    person_id: int | None = None,
) -> dict[str, list[Entry]]:
    """Existing entries on any of ``dates`` (FR-4).

    Scoped to ``person_id`` when given (single-person apply), otherwise
    across everyone (week-level roll-forward).
    """
    if not dates:
        return {}
    where = f"work_date IN ({in_placeholders(len(dates))})"
    params: list = list(dates)
    if person_id is not None:
        where = "person_id = ? AND " + where
        params = [person_id, *dates]
    rows = conn.execute(
        f"SELECT * FROM schedule_entry WHERE {where} ORDER BY work_date",
        params,
    ).fetchall()
    out: dict[str, list[Entry]] = {}
    for r in rows:
        out.setdefault(r["work_date"], []).append(Entry.from_row(r))
    return out


def apply_entry(
    conn: Connection,
    person_id: int,
    dates: list[str],
    entry_type: EntryType,
    *,
    start_time: str | None = None,
    end_time: str | None = None,
    note: str | None = None,
    overwrite: bool = False,
) -> ApplyResult:
    """Apply one entry to every date in ``dates`` (FR-3) in one transaction.

    v1 keeps one entry per (person, date): overwrite deletes existing rows
    for that pair then inserts. Without ``overwrite`` any existing entry on
    the selected dates raises :class:`OverwriteRequiredError` (FR-4).
    """
    if not dates:
        raise ValidationError("Select at least one date.")

    if conn.execute(
        "SELECT 1 FROM person WHERE id = ?", (person_id,)
    ).fetchone() is None:
        raise NotFoundError(f"No person with id {person_id}.")

    if entry_type is EntryType.SHIFT:
        if not start_time or not end_time:
            raise ValidationError("A shift needs both a start and end time.")
        crosses = validate_shift_times(start_time, end_time)
    elif start_time or end_time:
        raise ValidationError(f"{entry_type.value} cannot have times.")
    else:
        start_time = end_time = None
        crosses = False

    conflicts = find_conflicts(conn, dates, person_id)
    if conflicts and not overwrite:
        raise OverwriteRequiredError(conflicts)

    now = now_iso()
    overwritten = 0
    try:
        for d in dates:
            if overwrite:
                cur = conn.execute(
                    "DELETE FROM schedule_entry "
                    "WHERE person_id = ? AND work_date = ?",
                    (person_id, d),
                )
                overwritten += cur.rowcount
            insert_entry(
                conn, person_id=person_id, work_date=d,
                entry_type=entry_type.value, start_time=start_time,
                end_time=end_time, crosses_midnight=int(crosses),
                note=note, now=now,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return ApplyResult(created=len(dates), overwritten=overwritten)


def index_by_person_date(
    entries: list[Entry],
) -> dict[tuple[int, str], list[Entry]]:
    """Group entries by ``(person_id, work_date)`` for grid lookup.

    A list per cell — the schema allows multiple entries/day for a future
    version (PRD §11.4); v1 normally has 0 or 1.
    """
    grid: dict[tuple[int, str], list[Entry]] = {}
    for e in entries:
        grid.setdefault((e.person_id, e.work_date), []).append(e)
    return grid
