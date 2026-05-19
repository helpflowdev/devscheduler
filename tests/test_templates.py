"""Default-schedule template apply."""

from __future__ import annotations

from scheduler.entries import get_week_entries
from scheduler.models import EntryType
from scheduler.people import add_person, list_people
from scheduler.templates import (
    DEFAULT_TEMPLATE,
    apply_template,
    ensure_person,
)

MON = "2026-05-18"  # a Monday


def test_apply_creates_people_and_full_week(db):
    n = apply_template(db, MON)
    assert n == len(DEFAULT_TEMPLATE)
    names = {p.name for p in list_people(db)}
    assert {"JC", "Gio", "Karim", "Shierraine", "Marion"} <= names
    # 5 people × 7 days, every cell filled by the template.
    assert len(get_week_entries(db, MON)) == 35


def test_known_cells_match_screenshot(db):
    apply_template(db, MON)
    by = {(e.person_id, e.work_date): e for e in get_week_entries(db, MON)}
    pid = {p.name: p.id for p in list_people(db)}

    jc_mon = by[(pid["JC"], "2026-05-18")]
    assert (jc_mon.entry_type, jc_mon.start_time, jc_mon.end_time) == (
        EntryType.SHIFT, "07:00", "15:00")

    gio_mon = by[(pid["Gio"], "2026-05-18")]
    assert gio_mon.entry_type is EntryType.RD

    marion_wed = by[(pid["Marion"], "2026-05-20")]
    assert marion_wed.crosses_midnight is True  # 3:30 PM–12:00 AM

    # Updated roster: Gio Sun RD, Karim Sat RD, Marion Sat works.
    assert by[(pid["Gio"], "2026-05-24")].entry_type is EntryType.RD
    assert by[(pid["Karim"], "2026-05-23")].entry_type is EntryType.RD
    marion_sat = by[(pid["Marion"], "2026-05-23")]
    assert (marion_sat.entry_type, marion_sat.start_time) == (
        EntryType.SHIFT, "15:30")


def test_ensure_person_is_idempotent(db):
    a = add_person(db, "Gio").id
    assert ensure_person(db, "Gio") == a       # existing
    assert ensure_person(db, "gio") == a       # case-insensitive
    new = ensure_person(db, "Brand New")       # creates
    assert new != a


def test_apply_overwrites_existing_week(db):
    p = add_person(db, "JC").id
    from scheduler.entries import apply_entry
    apply_entry(db, p, ["2026-05-18"], EntryType.PTO)  # pre-existing
    apply_template(db, MON)
    jc_mon = [e for e in get_week_entries(db, MON)
              if e.person_id == p and e.work_date == "2026-05-18"]
    assert len(jc_mon) == 1
    assert jc_mon[0].entry_type is EntryType.SHIFT  # replaced
