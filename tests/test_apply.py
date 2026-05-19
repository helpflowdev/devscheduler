"""Bulk apply, validation, overwrite protection (M3)."""

from __future__ import annotations

import pytest

from scheduler.entries import (
    apply_entry,
    delete_entries,
    find_conflicts,
    get_week_entries,
    validate_shift_times,
)
from scheduler.errors import (
    NotFoundError,
    OverwriteRequiredError,
    ValidationError,
)
from scheduler.models import EntryType
from scheduler.people import add_person

WEEK = ["2026-05-18", "2026-05-19", "2026-05-20"]


# --- time validation ------------------------------------------------------

def test_normal_shift_not_crossing_midnight():
    assert validate_shift_times("09:00", "17:00") is False


def test_overnight_shift_crosses_midnight():
    assert validate_shift_times("22:00", "06:00") is True


def test_equal_times_rejected():
    with pytest.raises(ValidationError):
        validate_shift_times("09:00", "09:00")


@pytest.mark.parametrize("bad", ["24:00", "9:99", "noon", "08-00"])
def test_bad_time_format_rejected(bad):
    with pytest.raises(ValidationError):
        validate_shift_times("09:00", bad)


# --- bulk apply -----------------------------------------------------------

def test_bulk_apply_creates_one_per_date(db):
    p = add_person(db, "Alice")
    res = apply_entry(db, p.id, WEEK, EntryType.SHIFT,
                      start_time="09:00", end_time="17:00")
    assert (res.created, res.overwritten) == (3, 0)
    assert len(get_week_entries(db, "2026-05-18")) == 3


def test_shift_requires_times(db):
    p = add_person(db, "Bob")
    with pytest.raises(ValidationError):
        apply_entry(db, p.id, WEEK, EntryType.SHIFT)


def test_pto_rejects_times(db):
    p = add_person(db, "Cara")
    with pytest.raises(ValidationError):
        apply_entry(db, p.id, ["2026-05-18"], EntryType.PTO,
                    start_time="09:00", end_time="17:00")


def test_pto_applies_with_no_times(db):
    p = add_person(db, "Dana")
    res = apply_entry(db, p.id, ["2026-05-18"], EntryType.PTO)
    assert res.created == 1


def test_rd_applies_with_no_times(db):
    p = add_person(db, "Rey")
    res = apply_entry(db, p.id, ["2026-05-18"], EntryType.RD)
    assert res.created == 1
    row = get_week_entries(db, "2026-05-18")[0]
    assert row.entry_type is EntryType.RD
    assert row.start_time is None and row.end_time is None


def test_rd_rejects_times(db):
    p = add_person(db, "Rio")
    with pytest.raises(ValidationError):
        apply_entry(db, p.id, ["2026-05-18"], EntryType.RD,
                    start_time="09:00", end_time="17:00")


def test_delete_entries_removes_only_target(db):
    p = add_person(db, "Del")
    apply_entry(db, p.id, ["2026-05-18", "2026-05-19"], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    removed = delete_entries(db, p.id, ["2026-05-18"])
    assert removed == 1
    left = get_week_entries(db, "2026-05-18")
    assert [e.work_date for e in left] == ["2026-05-19"]


def test_delete_missing_date_is_noop(db):
    p = add_person(db, "Non")
    assert delete_entries(db, p.id, ["2026-05-18"]) == 0


def test_delete_no_dates_rejected(db):
    p = add_person(db, "Emp")
    with pytest.raises(ValidationError):
        delete_entries(db, p.id, [])


def test_no_dates_rejected(db):
    p = add_person(db, "Eve")
    with pytest.raises(ValidationError):
        apply_entry(db, p.id, [], EntryType.PTO)


def test_unknown_person_rejected(db):
    with pytest.raises(NotFoundError):
        apply_entry(db, 999, ["2026-05-18"], EntryType.PTO)


# --- overwrite protection (FR-4) -----------------------------------------

def test_conflict_blocks_without_overwrite(db):
    p = add_person(db, "Finn")
    apply_entry(db, p.id, ["2026-05-18"], EntryType.PTO)
    with pytest.raises(OverwriteRequiredError) as ei:
        apply_entry(db, p.id, ["2026-05-18", "2026-05-19"], EntryType.UTO)
    assert "2026-05-18" in ei.value.conflicts


def test_overwrite_replaces_not_duplicates(db):
    p = add_person(db, "Gus")
    apply_entry(db, p.id, ["2026-05-18"], EntryType.PTO)
    res = apply_entry(db, p.id, ["2026-05-18"], EntryType.SHIFT,
                      start_time="08:00", end_time="16:00", overwrite=True)
    assert (res.created, res.overwritten) == (1, 1)
    rows = get_week_entries(db, "2026-05-18")
    assert len(rows) == 1 and rows[0].entry_type is EntryType.SHIFT


def test_overwrite_across_mixed_dates_counts(db):
    """Overwrite where only some dates had entries."""
    p = add_person(db, "Hana")
    apply_entry(db, p.id, ["2026-05-18"], EntryType.PTO)  # 1 pre-existing
    res = apply_entry(db, p.id, WEEK, EntryType.SHIFT,
                      start_time="10:00", end_time="18:00", overwrite=True)
    assert (res.created, res.overwritten) == (3, 1)
    rows = get_week_entries(db, "2026-05-18")
    assert len(rows) == 3
    assert all(r.entry_type is EntryType.SHIFT for r in rows)


def test_overnight_shift_flag_persisted(db):
    p = add_person(db, "Ivy")
    apply_entry(db, p.id, ["2026-05-18"], EntryType.SHIFT,
                start_time="22:00", end_time="06:00")
    row = get_week_entries(db, "2026-05-18")[0]
    assert row.crosses_midnight is True
