"""Split shifts — several entries on one (person, date) (FR-10)."""

from __future__ import annotations

import pytest

from scheduler.coverage import peak_overlap, week_shift_segments
from scheduler.entries import (
    apply_entry,
    check_day_composition,
    day_entries,
    delete_entry,
    get_week_entries,
    index_by_person_date,
    shift_span,
    update_entry,
)
from scheduler.errors import NotFoundError, ValidationError
from scheduler.leaves import add_planned_leave, apply_planned_leaves_to_week
from scheduler.models import Entry, EntryType
from scheduler.people import add_person
from scheduler.templates import apply_template
from scheduler.weeks import copy_week

MON = "2026-05-18"
TUE = "2026-05-19"


def _shift(start, end, *, work_date=MON, person_id=1):
    return Entry(person_id=person_id, work_date=work_date,
                 entry_type=EntryType.SHIFT, start_time=start, end_time=end)


def _split(db, pid, *, date=MON):
    """A 6-10 AM / 4-8 PM split day."""
    apply_entry(db, pid, [date], EntryType.SHIFT,
                start_time="06:00", end_time="10:00")
    apply_entry(db, pid, [date], EntryType.SHIFT,
                start_time="16:00", end_time="20:00", mode="add")


# --- span arithmetic ------------------------------------------------------

def test_span_of_a_day_shift():
    assert shift_span("09:00", "17:00") == (540, 1020)


def test_span_of_an_overnight_shift_runs_past_midnight():
    assert shift_span("22:00", "06:00") == (1320, 1800)


def test_span_of_a_nearly_full_day_shift():
    assert shift_span("00:00", "23:59") == (0, 1439)


# --- composition rules (pure) --------------------------------------------

def test_empty_day_accepts_anything():
    check_day_composition([], EntryType.PTO)
    check_day_composition([], EntryType.SHIFT, "09:00", "17:00")


def test_non_overlapping_shifts_allowed():
    check_day_composition([_shift("06:00", "10:00")],
                          EntryType.SHIFT, "16:00", "20:00")


def test_touching_shifts_allowed():
    check_day_composition([_shift("09:00", "13:00")],
                          EntryType.SHIFT, "13:00", "17:00")


@pytest.mark.parametrize("start,end", [
    ("12:00", "20:00"),   # starts inside the existing block
    ("09:00", "17:00"),   # identical
    ("08:00", "12:00"),   # ends inside
    ("07:00", "23:00"),   # swallows it
])
def test_overlapping_shifts_rejected(start, end):
    with pytest.raises(ValidationError, match="overlap"):
        check_day_composition([_shift("09:00", "17:00")],
                              EntryType.SHIFT, start, end)


def test_overnight_shift_does_not_collide_with_that_morning():
    """22:00-06:00 runs into the *next* date, so 06:00-10:00 is free."""
    check_day_composition([_shift("22:00", "06:00")],
                          EntryType.SHIFT, "06:00", "10:00")


def test_overnight_shifts_can_still_overlap_each_other():
    with pytest.raises(ValidationError, match="overlap"):
        check_day_composition([_shift("22:00", "06:00")],
                              EntryType.SHIFT, "23:00", "04:00")


@pytest.mark.parametrize("whole_day", [
    EntryType.PTO, EntryType.UTO, EntryType.RD,
])
def test_whole_day_type_cannot_join_a_populated_day(whole_day):
    with pytest.raises(ValidationError, match="whole day"):
        check_day_composition([_shift("09:00", "17:00")], whole_day)


@pytest.mark.parametrize("whole_day", [
    EntryType.PTO, EntryType.UTO, EntryType.RD,
])
def test_shift_cannot_join_a_whole_day_entry(whole_day):
    existing = [Entry(person_id=1, work_date=MON, entry_type=whole_day)]
    with pytest.raises(ValidationError, match="whole day"):
        check_day_composition(existing, EntryType.SHIFT, "09:00", "17:00")


# --- add mode -------------------------------------------------------------

def test_add_mode_keeps_the_first_shift(db):
    p = add_person(db, "Split")
    _split(db, p.id)
    rows = day_entries(db, p.id, MON)
    assert [(r.start_time, r.end_time) for r in rows] == [
        ("06:00", "10:00"), ("16:00", "20:00")]


def test_replace_mode_still_replaces(db):
    p = add_person(db, "Solo")
    apply_entry(db, p.id, [MON], EntryType.SHIFT,
                start_time="06:00", end_time="10:00")
    apply_entry(db, p.id, [MON], EntryType.SHIFT,
                start_time="16:00", end_time="20:00", overwrite=True)
    assert len(day_entries(db, p.id, MON)) == 1


def test_add_mode_rejects_an_overlap(db):
    p = add_person(db, "Clash")
    apply_entry(db, p.id, [MON], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    with pytest.raises(ValidationError, match="overlap"):
        apply_entry(db, p.id, [MON], EntryType.SHIFT,
                    start_time="12:00", end_time="20:00", mode="add")
    assert len(day_entries(db, p.id, MON)) == 1


def test_add_mode_validates_every_date_before_writing(db):
    """One bad date fails the whole apply - no partial split week."""
    p = add_person(db, "Partial")
    apply_entry(db, p.id, [TUE], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    with pytest.raises(ValidationError):
        apply_entry(db, p.id, [MON, TUE], EntryType.SHIFT,
                    start_time="12:00", end_time="20:00", mode="add")
    assert day_entries(db, p.id, MON) == []          # untouched
    assert len(day_entries(db, p.id, TUE)) == 1


def test_add_mode_never_raises_overwrite_required(db):
    p = add_person(db, "NoPrompt")
    apply_entry(db, p.id, [MON], EntryType.SHIFT,
                start_time="06:00", end_time="10:00")
    res = apply_entry(db, p.id, [MON], EntryType.SHIFT,
                      start_time="16:00", end_time="20:00", mode="add")
    assert (res.created, res.overwritten) == (1, 0)


def test_unknown_mode_rejected(db):
    p = add_person(db, "Bad")
    with pytest.raises(ValidationError, match="mode"):
        apply_entry(db, p.id, [MON], EntryType.PTO, mode="merge")


def test_add_mode_across_a_bulk_range(db):
    p = add_person(db, "Bulk")
    apply_entry(db, p.id, [MON, TUE], EntryType.SHIFT,
                start_time="06:00", end_time="10:00")
    apply_entry(db, p.id, [MON, TUE], EntryType.SHIFT,
                start_time="16:00", end_time="20:00", mode="add")
    assert len(day_entries(db, p.id, MON)) == 2
    assert len(day_entries(db, p.id, TUE)) == 2


# --- per-entry update / delete -------------------------------------------

def test_update_entry_leaves_the_sibling_alone(db):
    p = add_person(db, "Edit")
    _split(db, p.id)
    first, second = day_entries(db, p.id, MON)
    update_entry(db, second.id, EntryType.SHIFT,
                 start_time="17:00", end_time="21:00")
    rows = day_entries(db, p.id, MON)
    assert [(r.start_time, r.end_time) for r in rows] == [
        ("06:00", "10:00"), ("17:00", "21:00")]
    assert rows[0].id == first.id


def test_update_entry_rejects_overlapping_the_sibling(db):
    p = add_person(db, "EditClash")
    _split(db, p.id)
    _, second = day_entries(db, p.id, MON)
    with pytest.raises(ValidationError, match="overlap"):
        update_entry(db, second.id, EntryType.SHIFT,
                     start_time="09:00", end_time="12:00")


def test_update_entry_rejects_whole_day_over_a_split(db):
    p = add_person(db, "EditPto")
    _split(db, p.id)
    _, second = day_entries(db, p.id, MON)
    with pytest.raises(ValidationError, match="whole day"):
        update_entry(db, second.id, EntryType.PTO)


def test_update_entry_can_still_retype_a_lone_entry(db):
    p = add_person(db, "Retype")
    apply_entry(db, p.id, [MON], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    only = day_entries(db, p.id, MON)[0]
    update_entry(db, only.id, EntryType.RD)
    row = day_entries(db, p.id, MON)[0]
    assert row.entry_type is EntryType.RD
    assert row.start_time is None and row.end_time is None


def test_update_entry_shift_needs_times(db):
    p = add_person(db, "NoTimes")
    apply_entry(db, p.id, [MON], EntryType.RD)
    only = day_entries(db, p.id, MON)[0]
    with pytest.raises(ValidationError):
        update_entry(db, only.id, EntryType.SHIFT)


def test_update_unknown_entry_rejected(db):
    with pytest.raises(NotFoundError):
        update_entry(db, 999, EntryType.RD)


def test_delete_entry_removes_only_that_half(db):
    p = add_person(db, "Half")
    _split(db, p.id)
    first, second = day_entries(db, p.id, MON)
    assert delete_entry(db, second.id) == 1
    left = day_entries(db, p.id, MON)
    assert len(left) == 1 and left[0].id == first.id


def test_delete_entry_is_idempotent(db):
    p = add_person(db, "Gone")
    apply_entry(db, p.id, [MON], EntryType.RD)
    only = day_entries(db, p.id, MON)[0]
    assert delete_entry(db, only.id) == 1
    assert delete_entry(db, only.id) == 0


# --- the rest of the app copes -------------------------------------------

def test_grid_index_gives_both_entries_in_one_cell(db):
    p = add_person(db, "Grid")
    _split(db, p.id)
    cell = index_by_person_date(get_week_entries(db, MON))[(p.id, MON)]
    assert len(cell) == 2


def test_copy_week_carries_a_split_day_forward(db):
    p = add_person(db, "Copy")
    _split(db, p.id)
    res = copy_week(db, MON, "2026-05-25")
    assert res.copied == 2
    rows = day_entries(db, p.id, "2026-05-25")
    assert [(r.start_time, r.end_time) for r in rows] == [
        ("06:00", "10:00"), ("16:00", "20:00")]


def test_planned_leave_wins_over_both_halves(db):
    p = add_person(db, "Leave")
    _split(db, p.id)
    add_planned_leave(db, person_id=p.id, start_date=MON, end_date=MON,
                      leave_type=EntryType.PTO)
    assert apply_planned_leaves_to_week(db, MON) == 1
    rows = day_entries(db, p.id, MON)
    assert len(rows) == 1 and rows[0].entry_type is EntryType.PTO


def test_template_can_define_a_split_day(db):
    tpl = [
        ("Ana", 0, "SHIFT", "06:00", "10:00"),
        ("Ana", 0, "SHIFT", "16:00", "20:00"),
    ]
    res = apply_template(db, MON, template=tpl)
    assert res.entries == 2
    rows = get_week_entries(db, MON)
    assert [(r.start_time, r.end_time) for r in rows] == [
        ("06:00", "10:00"), ("16:00", "20:00")]


def test_reapplying_a_split_template_does_not_duplicate(db):
    tpl = [
        ("Ana", 0, "SHIFT", "06:00", "10:00"),
        ("Ana", 0, "SHIFT", "16:00", "20:00"),
    ]
    apply_template(db, MON, template=tpl)
    apply_template(db, MON, template=tpl)
    assert len(get_week_entries(db, MON)) == 2


def test_coverage_draws_a_bar_per_half(db):
    p = add_person(db, "Cov")
    _split(db, p.id)
    segs = week_shift_segments(get_week_entries(db, MON), {p.id: "Cov"})
    assert len(segs) == 2
    # The halves don't overlap, so one person is never counted twice.
    assert peak_overlap(segs, MON) == 1
