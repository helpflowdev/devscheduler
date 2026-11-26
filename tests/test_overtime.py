"""Overtime — a SHIFT flagged ``is_ot`` (FR-12)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import pytest  # noqa: E402

from _lib import parse_type_choice, type_choice_of  # noqa: E402
from components.week_grid import (  # noqa: E402
    edit_cell_label,
    format_cell,
    hours_cell,
    manila_cell_map,
)
from scheduler.coverage import (  # noqa: E402
    week_minutes_by_person,
    week_shift_segments,
)
from scheduler.db import IntegrityError  # noqa: E402
from scheduler.entries import (  # noqa: E402
    apply_entry,
    day_entries,
    get_week_entries,
    get_week_people,
    update_entry,
)
from scheduler.errors import ValidationError  # noqa: E402
from scheduler.leaves import (  # noqa: E402
    add_planned_leave,
    apply_planned_leaves_to_week,
)
from scheduler.models import Entry, EntryType  # noqa: E402
from scheduler.people import add_person  # noqa: E402

MON = "2026-05-18"
TUE = "2026-05-19"


def _shift(start, end, *, ot=False, pid=1, date=MON, crosses=False):
    return Entry(person_id=pid, work_date=date, entry_type=EntryType.SHIFT,
                 start_time=start, end_time=end, crosses_midnight=crosses,
                 is_ot=ot)


def _regular_plus_ot(db, pid, *, date=MON):
    apply_entry(db, pid, [date], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    apply_entry(db, pid, [date], EntryType.SHIFT,
                start_time="17:00", end_time="19:00", mode="add", is_ot=True)


# --- storage + apply ------------------------------------------------------

def test_new_entries_default_to_not_ot(db):
    p = add_person(db, "Ana")
    apply_entry(db, p.id, [MON], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    (e,) = day_entries(db, p.id, MON)
    assert e.is_ot is False


def test_ot_added_beside_a_regular_shift(db):
    p = add_person(db, "Ana")
    _regular_plus_ot(db, p.id)
    day = day_entries(db, p.id, MON)
    assert [(e.start_time, e.is_ot) for e in day] == [
        ("09:00", False), ("17:00", True)]


def test_ot_may_not_overlap_the_regular_shift(db):
    p = add_person(db, "Ana")
    apply_entry(db, p.id, [MON], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    with pytest.raises(ValidationError, match="overlaps"):
        apply_entry(db, p.id, [MON], EntryType.SHIFT, start_time="16:00",
                    end_time="18:00", mode="add", is_ot=True)


def test_ot_on_a_rest_day_replaces_the_rd(db):
    p = add_person(db, "Ana")
    apply_entry(db, p.id, [MON], EntryType.RD)
    res = apply_entry(db, p.id, [MON], EntryType.SHIFT, start_time="10:00",
                      end_time="14:00", mode="add", is_ot=True)
    assert res.overwritten == 1
    (e,) = day_entries(db, p.id, MON)
    assert (e.entry_type, e.is_ot) == (EntryType.SHIFT, True)


def test_a_plain_shift_still_cannot_join_a_rest_day(db):
    p = add_person(db, "Ana")
    apply_entry(db, p.id, [MON], EntryType.RD)
    with pytest.raises(ValidationError, match="RD"):
        apply_entry(db, p.id, [MON], EntryType.SHIFT, start_time="10:00",
                    end_time="14:00", mode="add")


def test_ot_rejected_on_leave_and_nothing_is_written(db):
    """Bulk OT across a shift day and a PTO day fails as a whole."""
    p = add_person(db, "Ana")
    apply_entry(db, p.id, [MON], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    apply_entry(db, p.id, [TUE], EntryType.PTO)
    with pytest.raises(ValidationError, match="PTO"):
        apply_entry(db, p.id, [MON, TUE], EntryType.SHIFT,
                    start_time="17:00", end_time="19:00", mode="add",
                    is_ot=True)
    assert len(day_entries(db, p.id, MON)) == 1  # no OT half-written


@pytest.mark.parametrize("etype", [EntryType.PTO, EntryType.UTO,
                                   EntryType.RD])
def test_only_a_shift_can_be_ot(db, etype):
    p = add_person(db, "Ana")
    with pytest.raises(ValidationError, match="Only a shift"):
        apply_entry(db, p.id, [MON], etype, is_ot=True)


def test_db_check_blocks_ot_on_a_whole_day_type(db):
    p = add_person(db, "Ana")
    with pytest.raises(IntegrityError):
        db.execute(
            "INSERT INTO schedule_entry(person_id, work_date, entry_type,"
            " is_ot, created_at, updated_at) "
            "VALUES (?, ?, 'PTO', 1, 'x', 'x')", (p.id, MON))


def test_update_can_turn_a_shift_into_ot_and_back(db):
    p = add_person(db, "Ana")
    _regular_plus_ot(db, p.id)
    reg, ot = day_entries(db, p.id, MON)
    update_entry(db, ot.id, EntryType.SHIFT, start_time="17:00",
                 end_time="19:00", is_ot=False)
    assert [e.is_ot for e in day_entries(db, p.id, MON)] == [False, False]
    update_entry(db, reg.id, EntryType.SHIFT, start_time="09:00",
                 end_time="17:00", is_ot=True)
    assert [e.is_ot for e in day_entries(db, p.id, MON)] == [True, False]


def test_update_rd_to_ot_in_place(db):
    p = add_person(db, "Ana")
    apply_entry(db, p.id, [MON], EntryType.RD)
    (rd,) = day_entries(db, p.id, MON)
    update_entry(db, rd.id, EntryType.SHIFT, start_time="10:00",
                 end_time="12:00", is_ot=True)
    (e,) = day_entries(db, p.id, MON)
    assert (e.id, e.is_ot) == (rd.id, True)


def test_planned_leave_wipes_ot_too(db):
    p = add_person(db, "Ana")
    _regular_plus_ot(db, p.id)
    add_planned_leave(db, person_id=p.id, start_date=MON, end_date=MON,
                      leave_type=EntryType.PTO)
    apply_planned_leaves_to_week(db, MON)
    (e,) = day_entries(db, p.id, MON)
    assert (e.entry_type, e.is_ot) == (EntryType.PTO, False)


def test_roster_order_ignores_an_early_ot_block(db):
    early = add_person(db, "Early")   # regular 8 AM
    ot = add_person(db, "Overtime")   # regular 9 AM, but OT from 5 AM
    apply_entry(db, early.id, [MON], EntryType.SHIFT,
                start_time="08:00", end_time="16:00")
    apply_entry(db, ot.id, [MON], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    apply_entry(db, ot.id, [MON], EntryType.SHIFT, start_time="05:00",
                end_time="07:00", mode="add", is_ot=True)
    ents = get_week_entries(db, MON)
    order = [p.name for p in get_week_people(db, MON, entries=ents)]
    assert order == ["Early", "Overtime"]


# --- hours ----------------------------------------------------------------

def test_hours_split_regular_and_ot():
    week = [_shift("09:00", "17:00"), _shift("17:00", "19:00", ot=True),
            _shift("09:00", "17:00", date=TUE)]
    assert week_minutes_by_person(week) == {1: 960}
    assert week_minutes_by_person(week, ot=True) == {1: 120}


def test_overnight_ot_counts_its_full_length():
    entries = [_shift("22:00", "02:00", ot=True, crosses=True)]
    assert week_minutes_by_person(entries, ot=True) == {1: 240}
    assert week_minutes_by_person(entries) == {}


@pytest.mark.parametrize("reg,ot,text", [
    (2400, 0, "40h"),
    (2400, 120, "40h + 2h OT"),
    (0, 90, "0h + 1h 30m OT"),
])
def test_hours_cell(reg, ot, text):
    assert hours_cell(reg, ot) == text


# --- coverage -------------------------------------------------------------

def test_ot_segments_are_tagged_and_labelled():
    segs = week_shift_segments(
        [_shift("09:00", "17:00"), _shift("17:00", "19:00", ot=True)],
        {1: "Ana"})
    assert [(s.is_ot, s.label) for s in segs] == [
        (False, "9:00 AM–5:00 PM"), (True, "OT 5:00 PM–7:00 PM")]


def test_overnight_ot_splits_into_two_tagged_segments():
    segs = week_shift_segments(
        [_shift("22:00", "02:00", ot=True, crosses=True)], {1: "Ana"})
    assert len(segs) == 2 and all(s.is_ot for s in segs)


# --- grid display ---------------------------------------------------------

def test_cell_labels_ot_with_its_times():
    cell = format_cell([_shift("09:00", "17:00"),
                        _shift("17:00", "19:00", ot=True)], manila=False)
    assert cell == "9:00 AM–5:00 PM  ·  ⏱ OT 5:00 PM–7:00 PM"


def test_ot_only_cell():
    assert format_cell([_shift("10:00", "14:00", ot=True)],
                       manila=False) == "⏱ OT 10:00 AM–2:00 PM"


def test_edit_label_marks_the_ot_block():
    day = [_shift("09:00", "17:00"), _shift("17:00", "19:00", ot=True)]
    assert edit_cell_label(day, manila=False) == "9:00 AM + OT 5:00 PM"


def test_manila_map_keeps_the_ot_chip_on_both_halves():
    # 05:00–08:00 PDT OT → 8:00–11:00 PM Mon Manila (+15h): one piece.
    one = manila_cell_map([_shift("05:00", "08:00", ot=True)])
    assert list(one) == [(1, MON)]
    assert "⏱ OT 8:00 PM–11:00 PM" in one[(1, MON)][0]
    # 07:00–15:00 PDT OT crosses Manila midnight → chip on both days.
    two = manila_cell_map([_shift("07:00", "15:00", ot=True)])
    assert all("⏱ OT" in pieces[0] for pieces in two.values())
    assert set(two) == {(1, MON), (1, TUE)}


def test_type_choice_round_trip():
    assert parse_type_choice("OT") == (EntryType.SHIFT, True)
    assert parse_type_choice("SHIFT") == (EntryType.SHIFT, False)
    assert parse_type_choice("RD") == (EntryType.RD, False)
    assert type_choice_of(_shift("09:00", "17:00", ot=True)) == "OT"
    assert type_choice_of(_shift("09:00", "17:00")) == "SHIFT"
