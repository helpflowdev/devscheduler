"""Week query + viewer row policy (M2)."""

from __future__ import annotations

from scheduler.entries import (
    get_week_entries,
    get_week_people,
    index_by_person_date,
)
from scheduler.models import Entry, EntryType
from scheduler.people import add_person, deactivate_person


def _shift(pid, d, start):
    return Entry(person_id=pid, work_date=d, entry_type=EntryType.SHIFT,
                 start_time=start, end_time="23:00")


def test_people_ordered_by_earliest_shift_start(db):
    a = add_person(db, "Aaron")   # alphabetically first…
    z = add_person(db, "Zoe")     # …but starts earlier
    add_person(db, "Mia")         # no shift → after the shift workers
    ents = [
        _shift(a.id, "2026-05-19", "13:00"),
        _shift(z.id, "2026-05-18", "07:00"),
    ]
    order = [p.name for p in
             get_week_people(db, "2026-05-18", entries=ents)]
    assert order[:2] == ["Zoe", "Aaron"]      # by start, not alphabetical
    assert order[-1] == "Mia"                 # no shift → last


def test_earliest_across_week_used(db):
    p = add_person(db, "Pat")
    q = add_person(db, "Quinn")
    ents = [
        _shift(p.id, "2026-05-18", "10:00"),
        _shift(p.id, "2026-05-20", "06:00"),  # Pat's earliest = 06:00
        _shift(q.id, "2026-05-19", "08:00"),
    ]
    order = [x.name for x in
             get_week_people(db, "2026-05-18", entries=ents)]
    assert order == ["Pat", "Quinn"]


def _add_shift(db, person_id, work_date, start="09:00", end="17:00"):
    db.execute(
        "INSERT INTO schedule_entry"
        "(person_id, work_date, entry_type, start_time, end_time,"
        " created_at, updated_at) "
        "VALUES (?, ?, 'SHIFT', ?, ?, 'x', 'x')",
        (person_id, work_date, start, end),
    )
    db.commit()


def test_get_week_entries_filters_to_that_week(db):
    p = add_person(db, "Alice")
    _add_shift(db, p.id, "2026-05-13")  # Wed, in week of 2026-05-11
    _add_shift(db, p.id, "2026-05-20")  # next week
    week = get_week_entries(db, "2026-05-11")
    assert [e.work_date for e in week] == ["2026-05-13"]


def test_active_people_always_shown(db):
    add_person(db, "Bob")  # no entries this week
    people = get_week_people(db, "2026-05-11")
    assert [p.name for p in people] == ["Bob"]


def test_inactive_hidden_unless_has_entry_that_week(db):
    keep = add_person(db, "Cara")
    gone = add_person(db, "Dropped")
    _add_shift(db, gone.id, "2026-05-14")
    deactivate_person(db, gone.id)

    # Week WITH the inactive person's entry → they appear.
    names = [p.name for p in get_week_people(db, "2026-05-11")]
    assert names == ["Cara", "Dropped"]

    # A different week with no entry for them → hidden.
    names_other = [p.name for p in get_week_people(db, "2026-06-01")]
    assert names_other == ["Cara"]


def test_index_groups_by_person_and_date(db):
    p = add_person(db, "Eve")
    _add_shift(db, p.id, "2026-05-12", "09:00", "12:00")
    _add_shift(db, p.id, "2026-05-12", "13:00", "17:00")  # multi-entry/day
    grid = index_by_person_date(get_week_entries(db, "2026-05-11"))
    assert len(grid[(p.id, "2026-05-12")]) == 2
