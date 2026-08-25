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
from scheduler.timefmt import range_12h
from scheduler.util import in_placeholders, now_iso
from scheduler.weeks import iso, week_dates

_INSERT_SQL = (
    "INSERT INTO schedule_entry"
    "(person_id, work_date, entry_type, start_time, end_time,"
    " crosses_midnight, note, created_at, updated_at) "
    "VALUES (?,?,?,?,?,?,?,?,?)"
)

_UPDATE_SQL = (
    "UPDATE schedule_entry SET entry_type = ?, start_time = ?, "
    "end_time = ?, crosses_midnight = ?, note = ?, updated_at = ? "
    "WHERE id = ?"
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


def order_by_shift_start(
    people: list[Person], entries: list[Entry]
) -> list[Person]:
    """Roster order: earliest shift-start first, then whole-day/none,
    name as the tiebreaker.

    Each person gets the minimum SHIFT start time across the week's
    entries; people with no shift sort after those who do.
    """
    earliest: dict[int, int] = {}
    for e in entries:
        # Value compare (not enum identity) so this can't silently no-op
        # across environments/enum quirks.
        is_shift = getattr(e.entry_type, "value", e.entry_type) == "SHIFT"
        if is_shift and e.start_time:
            h, m = e.start_time.split(":")
            mins = int(h) * 60 + int(m)
            cur = earliest.get(e.person_id)
            if cur is None or mins < cur:
                earliest[e.person_id] = mins

    def key(p: Person):
        if p.id in earliest:
            return (0, earliest[p.id], p.name.lower())
        return (1, 0, p.name.lower())

    return sorted(people, key=key)


def get_week_people(
    conn: Connection,
    any_date: str,
    *,
    entries: list[Entry] | None = None,
) -> list[Person]:
    """Active people ∪ inactive-with-entries-this-week.

    With ``entries`` (already loaded for the week) rows are ordered by
    earliest shift start that week (then name); this also skips the
    correlated re-scan. Without ``entries``, name-sorted.
    """
    if entries is not None:
        with_entries = {e.person_id for e in entries}
        rows = conn.execute(
            "SELECT id, name, is_active, created_at FROM person "
            "WHERE is_active = 1"
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
        return order_by_shift_start(people, entries)

    dates = [iso(d) for d in week_dates(any_date)]
    rows = conn.execute(
        "SELECT id, name, is_active, created_at FROM person "
        "WHERE is_active = 1 "
        "   OR id IN (SELECT DISTINCT person_id FROM schedule_entry "
        f"             WHERE work_date IN ({in_placeholders(len(dates))})) "
        "ORDER BY lower(name)",
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


def shift_span(start: str, end: str) -> tuple[int, int]:
    """A shift as ``(start_min, end_min)`` on a single 0–2880 minute line.

    An overnight shift ends past 1440 (22:00–06:00 → ``(1320, 1800)``) so
    two shifts on the same ``work_date`` can be compared with plain
    interval arithmetic — the night block sits *after* the day's blocks
    instead of wrapping back over them.
    """
    s = _parse_hhmm(start, "Start time")
    e = _parse_hhmm(end, "End time")
    if e <= s:
        e += 24 * 60
    return s, e


def _normalize_times(
    entry_type: EntryType, start_time: str | None, end_time: str | None
) -> tuple[str | None, str | None, bool]:
    """Validate times against the type; return ``(start, end, crosses)``.

    SHIFT needs both times; the whole-day types must have neither.
    """
    if entry_type is EntryType.SHIFT:
        if not start_time or not end_time:
            raise ValidationError("A shift needs both a start and end time.")
        return start_time, end_time, validate_shift_times(start_time, end_time)
    if start_time or end_time:
        raise ValidationError(f"{entry_type.value} cannot have times.")
    return None, None, False


def check_day_composition(
    existing: list[Entry],
    entry_type: EntryType,
    start_time: str | None = None,
    end_time: str | None = None,
) -> None:
    """Guard adding an entry *alongside* a ``(person, date)``'s entries.

    A day may hold several SHIFTs — a split schedule — as long as none of
    them overlap; touching blocks (09:00–13:00 + 13:00–17:00) are fine.
    PTO/UTO/RD cover the whole day and are exclusive: they can neither
    join a populated day nor be joined. Pure — no DB access (FR-10).

    Only same-date overlap is checked; an overnight shift is not compared
    against the *next* date's entries.
    """
    if not existing:
        return

    if entry_type is not EntryType.SHIFT:
        raise ValidationError(
            f"{entry_type.value} covers the whole day, so it can't be added "
            "alongside another entry — replace the day instead."
        )

    blocking = next(
        (e for e in existing if e.entry_type is not EntryType.SHIFT), None
    )
    if blocking is not None:
        raise ValidationError(
            f"That day is already {blocking.entry_type.value}, which covers "
            "the whole day — replace the day instead of adding to it."
        )

    s, t = shift_span(start_time, end_time)
    for e in existing:
        es, et = shift_span(e.start_time, e.end_time)
        if s < et and es < t:
            raise ValidationError(
                "That overlaps an existing shift "
                f"({range_12h(e.start_time, e.end_time)}) — the shifts in a "
                "split day must not overlap."
            )


def day_entries(
    conn: Connection, person_id: int, work_date: str
) -> list[Entry]:
    """Everything a single ``(person, date)`` cell holds, earliest first."""
    rows = conn.execute(
        "SELECT * FROM schedule_entry WHERE person_id = ? AND work_date = ? "
        "ORDER BY start_time",
        (person_id, work_date),
    ).fetchall()
    return [Entry.from_row(r) for r in rows]


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
    mode: str = "replace",
) -> ApplyResult:
    """Apply one entry to every date in ``dates`` (FR-3) in one transaction.

    ``mode="replace"`` (the default) keeps one entry per (person, date):
    ``overwrite`` deletes the existing rows for that pair then inserts, and
    without it any existing entry on the selected dates raises
    :class:`OverwriteRequiredError` (FR-4).

    ``mode="add"`` inserts *alongside* whatever the day already holds — a
    split shift (FR-10). There is no overwrite prompt; instead every target
    date is checked by :func:`check_day_composition` **before** anything is
    written, so an illegal date fails the whole apply rather than half of it.
    """
    if not dates:
        raise ValidationError("Select at least one date.")
    if mode not in ("replace", "add"):
        raise ValidationError(f"Unknown apply mode {mode!r}.")

    if conn.execute(
        "SELECT 1 FROM person WHERE id = ?", (person_id,)
    ).fetchone() is None:
        raise NotFoundError(f"No person with id {person_id}.")

    start_time, end_time, crosses = _normalize_times(
        entry_type, start_time, end_time
    )

    existing = find_conflicts(conn, dates, person_id)
    if mode == "add":
        for d in dates:
            check_day_composition(
                existing.get(d, []), entry_type, start_time, end_time
            )
    elif existing and not overwrite:
        raise OverwriteRequiredError(existing)

    replacing = mode == "replace" and overwrite
    now = now_iso()
    overwritten = 0
    try:
        for d in dates:
            if replacing:
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


def get_entry(conn: Connection, entry_id: int) -> Entry:
    """One entry by id. Raises :class:`NotFoundError`."""
    row = conn.execute(
        "SELECT * FROM schedule_entry WHERE id = ?", (entry_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"No entry with id {entry_id}.")
    return Entry.from_row(row)


def update_entry(
    conn: Connection,
    entry_id: int,
    entry_type: EntryType,
    *,
    start_time: str | None = None,
    end_time: str | None = None,
    note: str | None = None,
) -> None:
    """Edit one entry in place, leaving the day's other entries alone.

    Needed once a day can hold a split shift: the old "overwrite the whole
    cell" edit would take the sibling shift with it. The change is checked
    against the day's *other* entries, so an edit can't be used to sneak
    past the no-overlap rule.
    """
    current = get_entry(conn, entry_id)
    start_time, end_time, crosses = _normalize_times(
        entry_type, start_time, end_time
    )
    siblings = [
        e for e in day_entries(conn, current.person_id, current.work_date)
        if e.id != entry_id
    ]
    check_day_composition(siblings, entry_type, start_time, end_time)

    try:
        conn.execute(_UPDATE_SQL, (
            entry_type.value, start_time, end_time, int(crosses),
            note, now_iso(), entry_id,
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def delete_entry(conn: Connection, entry_id: int) -> int:
    """Delete a single entry by id — one half of a split day, not the day.

    Idempotent: deleting an id that's already gone returns 0.
    """
    try:
        cur = conn.execute(
            "DELETE FROM schedule_entry WHERE id = ?", (entry_id,)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return cur.rowcount


def delete_entries(
    conn: Connection, person_id: int, dates: list[str]
) -> int:
    """Delete ``person_id``'s entries on ``dates``. Returns rows removed.

    Single transaction. Idempotent — deleting a date with no entry is a
    no-op (returns a smaller count), not an error.
    """
    if not dates:
        raise ValidationError("Select at least one date.")
    try:
        removed = 0
        for d in dates:
            cur = conn.execute(
                "DELETE FROM schedule_entry "
                "WHERE person_id = ? AND work_date = ?",
                (person_id, d),
            )
            removed += cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return removed


def index_by_person_date(
    entries: list[Entry],
) -> dict[tuple[int, str], list[Entry]]:
    """Group entries by ``(person_id, work_date)`` for grid lookup.

    A list per cell — a day holds 0 or 1 entries normally, or several
    SHIFTs on a split day (FR-10).
    """
    grid: dict[tuple[int, str], list[Entry]] = {}
    for e in entries:
        grid.setdefault((e.person_id, e.work_date), []).append(e)
    return grid
