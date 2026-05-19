"""Copy week → next week (M4 / FR-5)."""

from __future__ import annotations

import pytest

from scheduler.entries import apply_entry, get_week_entries
from scheduler.errors import OverwriteRequiredError, ValidationError
from scheduler.models import EntryType
from scheduler.people import add_person
from scheduler.weeks import clear_week, copy_week


def test_clear_week_removes_only_that_week(db):
    p = add_person(db, "Zoe")
    apply_entry(db, p.id, ["2026-05-18", "2026-05-20"], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    apply_entry(db, p.id, ["2026-05-25"], EntryType.PTO)  # next week
    removed = clear_week(db, "2026-05-18")
    assert removed == 2
    assert get_week_entries(db, "2026-05-18") == []
    assert len(get_week_entries(db, "2026-05-25")) == 1  # untouched


def test_clear_empty_week_is_noop(db):
    assert clear_week(db, "2026-05-18") == 0

SRC = "2026-05-18"  # Monday
NXT = "2026-05-25"  # next Monday


def _seed(db):
    p = add_person(db, "Alice")
    apply_entry(db, p.id, ["2026-05-18", "2026-05-22"], EntryType.SHIFT,
                start_time="09:00", end_time="17:00")
    apply_entry(db, p.id, ["2026-05-20"], EntryType.PTO)
    return p


def test_exact_copy_preserves_weekday_and_type(db):
    _seed(db)
    res = copy_week(db, SRC, NXT)
    assert (res.copied, res.overwritten) == (3, 0)

    nxt = {e.work_date: e for e in get_week_entries(db, NXT)}
    assert set(nxt) == {"2026-05-25", "2026-05-27", "2026-05-29"}  # Mon/Wed/Fri
    assert nxt["2026-05-27"].entry_type is EntryType.PTO
    assert nxt["2026-05-25"].start_time == "09:00"
    # Source week is untouched.
    assert len(get_week_entries(db, SRC)) == 3


def test_same_week_rejected(db):
    _seed(db)
    with pytest.raises(ValidationError):
        copy_week(db, SRC, "2026-05-20")  # same week as SRC


def test_empty_source_rejected(db):
    add_person(db, "Bob")
    with pytest.raises(ValidationError):
        copy_week(db, SRC, NXT)


def test_conflict_blocks_without_overwrite(db):
    p = _seed(db)
    apply_entry(db, p.id, ["2026-05-25"], EntryType.UTO)  # occupies dst week
    with pytest.raises(OverwriteRequiredError) as ei:
        copy_week(db, SRC, NXT)
    assert "2026-05-25" in ei.value.conflicts


def test_overwrite_clears_destination_week(db):
    p = _seed(db)
    apply_entry(db, p.id, ["2026-05-26"], EntryType.UTO)  # 1 in dst week
    res = copy_week(db, SRC, NXT, overwrite=True)
    assert (res.copied, res.overwritten) == (3, 1)
    nxt = get_week_entries(db, NXT)
    assert len(nxt) == 3  # the stray UTO was cleared, not kept
    assert not any(e.entry_type is EntryType.UTO for e in nxt)


def test_copy_is_atomic_on_failure(db):
    """A failure mid-batch must roll the whole copy back (single txn)."""
    _seed(db)  # src → dst dates 2026-05-25 (Mon), 27 (Wed), 29 (Fri)
    # SQLite trigger aborts the *second* inserted row; the first must not
    # persist (single transaction). SQLite-only, which is the test backend.
    db.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON schedule_entry "
        "WHEN NEW.work_date = '2026-05-27' "
        "BEGIN SELECT RAISE(ABORT, 'injected'); END"
    )
    db.commit()
    try:
        with pytest.raises(Exception):
            copy_week(db, SRC, NXT)
        assert len(get_week_entries(db, NXT)) == 0  # fully rolled back
    finally:
        db.execute("DROP TRIGGER boom")
        db.commit()
