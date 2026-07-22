"""Planned-leave registry and its overlay onto built weeks."""

from __future__ import annotations

import pytest

from scheduler.entries import apply_entry, get_week_entries
from scheduler.errors import NotFoundError, ValidationError
from scheduler.leaves import (
    add_planned_leave,
    apply_planned_leaves_to_week,
    delete_planned_leave,
    leaves_overlapping,
    list_planned_leaves,
)
from scheduler.models import EntryType
from scheduler.people import add_person
from scheduler.templates import apply_template
from scheduler.weeks import copy_week, iso, week_dates

SRC = "2026-05-18"  # Monday
NXT = "2026-05-25"  # next Monday
NXT_WED = "2026-05-27"


def _pto(db, pid, start, end="", ltype=EntryType.PTO):
    return add_planned_leave(
        db, person_id=pid, start_date=start, end_date=end or start,
        leave_type=ltype,
    )


# ---------------------------------------------------------------------------
# CRUD + validation
# ---------------------------------------------------------------------------
def test_add_and_list_roundtrip(db):
    p = add_person(db, "Alice")
    lv = _pto(db, p.id, "2026-05-27", "2026-05-29")
    assert lv.id is not None
    assert lv.person_name == "Alice"
    assert lv.leave_type is EntryType.PTO
    all_ = list_planned_leaves(db)
    assert [x.id for x in all_] == [lv.id]


def test_end_before_start_rejected(db):
    p = add_person(db, "Alice")
    with pytest.raises(ValidationError):
        _pto(db, p.id, "2026-05-29", "2026-05-27")


def test_shift_type_rejected(db):
    p = add_person(db, "Alice")
    with pytest.raises(ValidationError):
        add_planned_leave(db, person_id=p.id, start_date="2026-05-27",
                          end_date="2026-05-27", leave_type=EntryType.SHIFT)


def test_unknown_person_rejected(db):
    with pytest.raises(NotFoundError):
        _pto(db, 999, "2026-05-27")


def test_delete_removes_from_registry(db):
    p = add_person(db, "Alice")
    lv = _pto(db, p.id, "2026-05-27")
    assert delete_planned_leave(db, lv.id) == 1
    assert list_planned_leaves(db) == []


def test_since_hides_fully_past_leaves(db):
    p = add_person(db, "Alice")
    _pto(db, p.id, "2026-01-05", "2026-01-06")   # past
    keep = _pto(db, p.id, "2026-05-27")          # on/after cutoff
    got = list_planned_leaves(db, since="2026-05-01")
    assert [x.id for x in got] == [keep.id]


# ---------------------------------------------------------------------------
# Overlap detection
# ---------------------------------------------------------------------------
def test_leaves_overlapping_clips_to_week(db):
    p = add_person(db, "Alice")
    # Spans the weekend before NXT into midweek — only the in-week part counts.
    _pto(db, p.id, "2026-05-23", "2026-05-27")
    wk = [iso(d) for d in week_dates(NXT)]
    hits = leaves_overlapping(db, wk)
    assert len(hits) == 1


def test_no_overlap_returns_empty(db):
    p = add_person(db, "Alice")
    _pto(db, p.id, "2026-06-15")  # far future week
    assert leaves_overlapping(db, [iso(d) for d in week_dates(NXT)]) == []


# ---------------------------------------------------------------------------
# Overlay via copy-forward
# ---------------------------------------------------------------------------
def test_copy_overlays_leave_over_shift(db):
    """A leave filed on the destination week wins over the copied shift."""
    p = add_person(db, "Alice")
    apply_entry(db, p.id, [SRC, "2026-05-20"], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")  # Mon + Wed shifts
    _pto(db, p.id, NXT_WED)  # PTO on the copied-into Wednesday

    res = copy_week(db, SRC, NXT)
    assert res.copied == 2
    assert res.leaves_applied == 1

    by = {e.work_date: e for e in get_week_entries(db, NXT)}
    assert by[NXT_WED].entry_type is EntryType.PTO      # shift replaced
    assert by["2026-05-25"].entry_type is EntryType.SHIFT  # untouched Monday


def test_copy_leave_stays_single_entry_per_day(db):
    p = add_person(db, "Alice")
    apply_entry(db, p.id, ["2026-05-20"], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    _pto(db, p.id, NXT_WED)
    copy_week(db, SRC, NXT)
    wed = [e for e in get_week_entries(db, NXT) if e.work_date == NXT_WED]
    assert len(wed) == 1  # one entry/date preserved (overwrite, not append)


def test_copy_applies_leave_for_person_absent_from_source(db):
    """A leave for someone with no shift that week still lands."""
    a = add_person(db, "Alice")
    b = add_person(db, "Bob")
    apply_entry(db, a.id, [SRC], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")  # only Alice has shifts
    _pto(db, b.id, NXT_WED)  # Bob has no shift but filed leave

    res = copy_week(db, SRC, NXT)
    assert res.leaves_applied == 1
    bob = [e for e in get_week_entries(db, NXT)
           if e.person_id == b.id and e.work_date == NXT_WED]
    assert len(bob) == 1 and bob[0].entry_type is EntryType.PTO


# ---------------------------------------------------------------------------
# Overlay via template + standalone apply
# ---------------------------------------------------------------------------
def test_template_overlays_planned_leave(db):
    p = add_person(db, "JC")
    _pto(db, p.id, "2026-05-19", ltype=EntryType.UTO)  # Tue of the templated wk
    res = apply_template(db, SRC)
    assert res.leaves_applied == 1
    jc_tue = [e for e in get_week_entries(db, SRC)
              if e.person_id == p.id and e.work_date == "2026-05-19"]
    assert jc_tue[0].entry_type is EntryType.UTO  # replaced the templated shift


def test_apply_to_week_is_idempotent(db):
    p = add_person(db, "Alice")
    apply_entry(db, p.id, [NXT_WED], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    _pto(db, p.id, NXT_WED)
    assert apply_planned_leaves_to_week(db, NXT) == 1
    assert apply_planned_leaves_to_week(db, NXT) == 1  # re-run stable
    wed = [e for e in get_week_entries(db, NXT) if e.work_date == NXT_WED]
    assert len(wed) == 1 and wed[0].entry_type is EntryType.PTO
