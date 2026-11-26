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


def test_copy_preserves_weekday_and_skips_pto(db):
    _seed(db)
    res = copy_week(db, SRC, NXT)
    assert (res.copied, res.overwritten, res.skipped) == (2, 0, 1)

    nxt = {e.work_date: e for e in get_week_entries(db, NXT)}
    assert set(nxt) == {"2026-05-25", "2026-05-29"}  # Mon/Fri; PTO not carried
    assert nxt["2026-05-25"].start_time == "09:00"
    # Alice isn't in the standing schedule, so her ex-PTO Wed stays empty
    # and is reported rather than silently dropped.
    assert res.filled == 0
    assert res.unfilled == [("Alice", "2026-05-27")]
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
    assert (res.copied, res.overwritten) == (2, 1)
    nxt = get_week_entries(db, NXT)
    assert len(nxt) == 2  # the stray UTO was cleared, not kept
    assert not any(e.entry_type is EntryType.UTO for e in nxt)


def test_copy_is_atomic_on_failure(db):
    """A failure mid-batch must roll the whole copy back (single txn)."""
    _seed(db)  # carried shifts land on 2026-05-25 (Mon) and 29 (Fri)
    # SQLite trigger aborts the *second* inserted row; the first must not
    # persist (single transaction). SQLite-only, which is the test backend.
    db.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON schedule_entry "
        "WHEN NEW.work_date = '2026-05-29' "
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


# ---------------------------------------------------------------------------
# FR-13 — OT/PTO/UTO aren't carried; emptied days use the standing schedule
# ---------------------------------------------------------------------------
from scheduler.entries import day_entries  # noqa: E402
from scheduler.leaves import add_planned_leave  # noqa: E402

NXT_MON, NXT_WED, NXT_SAT = "2026-05-25", "2026-05-27", "2026-05-30"


def _cell(db, pid, d):
    return [(e.entry_type, e.start_time, e.end_time, e.is_ot)
            for e in day_entries(db, pid, d)]


def test_pto_day_refilled_from_standing_shift(db):
    jc = add_person(db, "JC")  # standing: 7 AM–3 PM Mon–Fri
    apply_entry(db, jc.id, ["2026-05-18"], EntryType.SHIFT,
                start_time="07:00", end_time="15:00")
    apply_entry(db, jc.id, ["2026-05-20"], EntryType.PTO)
    res = copy_week(db, SRC, NXT)
    assert (res.copied, res.skipped, res.filled) == (1, 1, 1)
    assert res.unfilled == []
    assert _cell(db, jc.id, NXT_WED) == [
        (EntryType.SHIFT, "07:00", "15:00", False)]


def test_uto_day_refilled_with_standing_rest_day(db):
    gio = add_person(db, "Gio")  # standing: RD Mon
    apply_entry(db, gio.id, ["2026-05-18"], EntryType.UTO)
    res = copy_week(db, SRC, NXT)
    assert res.filled == 1
    assert _cell(db, gio.id, NXT_MON) == [(EntryType.RD, None, None, False)]


def test_standing_overnight_fill_sets_crosses_midnight(db):
    marion = add_person(db, "Marion")  # standing: 3:30 PM–12:00 AM Wed
    apply_entry(db, marion.id, ["2026-05-20"], EntryType.PTO)
    copy_week(db, SRC, NXT)
    (wed,) = day_entries(db, marion.id, NXT_WED)
    assert (wed.start_time, wed.end_time, wed.crosses_midnight) == (
        "15:30", "00:00", True)


def test_ot_not_carried_but_its_regular_shift_is(db):
    jc = add_person(db, "JC")
    apply_entry(db, jc.id, ["2026-05-18"], EntryType.SHIFT,
                start_time="07:00", end_time="15:00")
    apply_entry(db, jc.id, ["2026-05-18"], EntryType.SHIFT,
                start_time="15:00", end_time="17:00", mode="add", is_ot=True)
    res = copy_week(db, SRC, NXT)
    assert (res.copied, res.skipped, res.filled) == (1, 1, 0)
    assert _cell(db, jc.id, NXT_MON) == [
        (EntryType.SHIFT, "07:00", "15:00", False)]


def test_ot_on_a_rest_day_reverts_to_the_standing_rest_day(db):
    jc = add_person(db, "JC")  # standing: RD Sat
    apply_entry(db, jc.id, ["2026-05-23"], EntryType.RD)
    apply_entry(db, jc.id, ["2026-05-23"], EntryType.SHIFT,
                start_time="09:00", end_time="13:00", mode="add", is_ot=True)
    res = copy_week(db, SRC, NXT)
    assert (res.skipped, res.filled) == (1, 1)
    assert _cell(db, jc.id, NXT_SAT) == [(EntryType.RD, None, None, False)]


def test_split_standing_day_is_filled_in_full(db):
    p = add_person(db, "Split")
    tpl = [("Split", 2, "SHIFT", "06:00", "10:00"),
           ("Split", 2, "SHIFT", "16:00", "20:00")]
    apply_entry(db, p.id, ["2026-05-20"], EntryType.PTO)
    res = copy_week(db, SRC, NXT, template=tpl)
    assert res.filled == 1
    assert [(s, e) for _, s, e, _ in _cell(db, p.id, NXT_WED)] == [
        ("06:00", "10:00"), ("16:00", "20:00")]


def test_planned_leave_still_wins_over_the_standing_fill(db):
    jc = add_person(db, "JC")
    apply_entry(db, jc.id, ["2026-05-20"], EntryType.PTO)  # last week
    add_planned_leave(db, person_id=jc.id, start_date=NXT_WED,
                      end_date=NXT_WED, leave_type=EntryType.UTO)
    res = copy_week(db, SRC, NXT)
    assert res.leaves_applied == 1
    assert _cell(db, jc.id, NXT_WED) == [(EntryType.UTO, None, None, False)]


def test_rest_days_and_notes_still_copy_unchanged(db):
    p = add_person(db, "Nora")  # not in the standing schedule
    apply_entry(db, p.id, ["2026-05-23"], EntryType.RD)
    apply_entry(db, p.id, ["2026-05-18"], EntryType.SHIFT,
                start_time="09:00", end_time="17:00", note="front desk")
    res = copy_week(db, SRC, NXT)
    assert (res.copied, res.skipped, res.unfilled) == (2, 0, [])
    (mon,) = day_entries(db, p.id, NXT_MON)
    assert mon.note == "front desk"
    assert _cell(db, p.id, NXT_SAT) == [(EntryType.RD, None, None, False)]
