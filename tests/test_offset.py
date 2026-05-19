"""Copy-forward with a time offset / slide (M5 / FR-6)."""

from __future__ import annotations

import pytest

from scheduler.entries import apply_entry, get_week_entries
from scheduler.errors import ValidationError
from scheduler.models import EntryType
from scheduler.people import add_person
from scheduler.weeks import (
    copy_week_with_offset,
    preview_offset,
    shift_shift_times,
)

SRC = "2026-05-18"  # Monday
NXT = "2026-05-25"  # next Monday


# --- pure offset math -----------------------------------------------------

def test_positive_offset_no_wrap():
    assert shift_shift_times("09:00", "17:00", 90) == ("10:30", "18:30", False)


def test_negative_offset():
    assert shift_shift_times("09:00", "17:00", -60) == ("08:00", "16:00", False)


def test_offset_wraps_and_recomputes_crosses_midnight():
    # 22:00–23:00 shifted +3h → 01:00–02:00 (next day); not crossing.
    assert shift_shift_times("22:00", "23:00", 180) == ("01:00", "02:00", False)
    # 16:00–23:00 shifted +9h → 01:00–08:00 next day, start wraps past end?
    # 16:00+9h=01:00, 23:00+9h=08:00 → 01:00–08:00, not crossing.
    assert shift_shift_times("16:00", "23:00", 540) == ("01:00", "08:00", False)


def test_offset_can_create_overnight():
    # 20:00–23:00 shifted +5h → 01:00–04:00 (clean). Use a case that crosses:
    # 22:00–02:00 (already overnight) shifted +1h → 23:00–03:00, still crosses.
    assert shift_shift_times("22:00", "02:00", 60) == ("23:00", "03:00", True)


# --- DB apply -------------------------------------------------------------

def _seed(db):
    p = add_person(db, "Alice")
    apply_entry(db, p.id, ["2026-05-18", "2026-05-22"], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    apply_entry(db, p.id, ["2026-05-20"], EntryType.PTO)
    return p


def test_offset_applies_to_shifts_only(db):
    _seed(db)
    res = copy_week_with_offset(db, SRC, NXT, 60)  # +1h
    assert res.copied == 3
    by_date = {e.work_date: e for e in get_week_entries(db, NXT)}
    assert by_date["2026-05-25"].start_time == "10:00"  # shift moved
    assert by_date["2026-05-25"].end_time == "18:00"
    assert by_date["2026-05-27"].entry_type is EntryType.PTO  # unchanged
    assert by_date["2026-05-27"].start_time is None


def test_zero_offset_rejected(db):
    _seed(db)
    with pytest.raises(ValidationError):
        copy_week_with_offset(db, SRC, NXT, 0)


def test_negative_offset_persists(db):
    _seed(db)
    copy_week_with_offset(db, SRC, NXT, -90)  # -1:30
    mon = {e.work_date: e for e in get_week_entries(db, NXT)}["2026-05-25"]
    assert (mon.start_time, mon.end_time) == ("07:30", "15:30")


def test_preview_does_not_write(db):
    _seed(db)
    rows = preview_offset(db, SRC, NXT, 60)
    assert get_week_entries(db, NXT) == []  # nothing written

    shifts = [r for r in rows if r.entry_type == "SHIFT"]
    pto = [r for r in rows if r.entry_type == "PTO"]
    assert any(r.old == "09:00–17:00" and r.new == "10:00–18:00"
               for r in shifts)
    assert pto and pto[0].old == "" and pto[0].new == ""
    assert all(r.dst_date.startswith("2026-05-2") or
               r.dst_date.startswith("2026-05-3") for r in rows)
