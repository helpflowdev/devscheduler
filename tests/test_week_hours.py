"""Weekly scheduled-hours totals shown beside each name (FR-10)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import pytest  # noqa: E402

from components.week_grid import edit_cell_label  # noqa: E402
from scheduler.coverage import week_minutes_by_person  # noqa: E402
from scheduler.models import Entry, EntryType  # noqa: E402
from scheduler.timefmt import hours_label  # noqa: E402

MON = "2026-05-18"


def _shift(start, end, *, pid=1, date=MON, crosses=False):
    return Entry(person_id=pid, work_date=date, entry_type=EntryType.SHIFT,
                 start_time=start, end_time=end, crosses_midnight=crosses)


# --- label ----------------------------------------------------------------

@pytest.mark.parametrize("minutes,text", [
    (480, "8h"),
    (450, "7h 30m"),
    (60, "1h"),
    (5, "0h 5m"),
    (0, "0h"),
    (-10, "0h"),      # never render a negative total
    (2400, "40h"),
])
def test_hours_label(minutes, text):
    assert hours_label(minutes) == text


# --- totals ---------------------------------------------------------------

def test_no_entries_is_empty():
    assert week_minutes_by_person([]) == {}


def test_single_shift():
    assert week_minutes_by_person([_shift("09:00", "17:00")]) == {1: 480}


def test_split_day_sums_both_blocks():
    day = [_shift("06:00", "10:00"), _shift("16:00", "20:00")]
    assert week_minutes_by_person(day) == {1: 480}


def test_overnight_shift_counts_its_full_length():
    entries = [_shift("22:00", "06:00", crosses=True)]
    assert week_minutes_by_person(entries) == {1: 480}


def test_whole_day_types_carry_no_hours():
    entries = [
        Entry(person_id=1, work_date=MON, entry_type=EntryType.PTO),
        Entry(person_id=1, work_date=MON, entry_type=EntryType.UTO),
        Entry(person_id=1, work_date=MON, entry_type=EntryType.RD),
    ]
    assert week_minutes_by_person(entries) == {}


def test_totals_are_per_person():
    entries = [
        _shift("09:00", "17:00", pid=1),
        _shift("09:00", "17:00", pid=1, date="2026-05-19"),
        _shift("10:00", "14:30", pid=2),
    ]
    assert week_minutes_by_person(entries) == {1: 960, 2: 270}


def test_a_full_week_of_eights_reads_forty_hours():
    week = [_shift("09:00", "17:00", date=f"2026-05-{18 + i}")
            for i in range(5)]
    totals = week_minutes_by_person(week)
    assert hours_label(totals[1]) == "40h"


# --- compact edit-mode cell label ----------------------------------------

def test_edit_label_empty_cell():
    assert edit_cell_label([], manila=False) == "✏️"


def test_edit_label_single_entry_shows_the_range():
    assert edit_cell_label([_shift("09:00", "17:00")],
                           manila=False) == "9:00 AM–5:00 PM"


def test_edit_label_split_day_shows_start_times():
    day = [_shift("06:00", "10:00"), _shift("16:00", "20:00")]
    assert edit_cell_label(day, manila=False) == "6:00 AM + 4:00 PM"


def test_edit_label_split_day_in_manila():
    # 06:00 PDT +15h → 9:00 PM; 16:00 → 7:00 AM.
    day = [_shift("06:00", "10:00"), _shift("16:00", "20:00")]
    assert edit_cell_label(day, manila=True) == "9:00 PM + 7:00 AM"


def test_edit_label_mixes_a_type_tag_in():
    day = [_shift("06:00", "10:00"),
           Entry(person_id=1, work_date=MON, entry_type=EntryType.PTO)]
    assert edit_cell_label(day, manila=False) == "6:00 AM + PTO"
