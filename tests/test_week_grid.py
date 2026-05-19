"""Pure cell formatting for the viewer grid (M2)."""

from __future__ import annotations

import sys
from pathlib import Path

# week_grid lives in the app/ layer; make it importable for this unit test.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from components.week_grid import format_cell  # noqa: E402
from scheduler.models import Entry, EntryType  # noqa: E402


def _shift(start, end, *, crosses=False):
    return Entry(
        person_id=1,
        work_date="2026-07-01",  # PDT → Pacific+15h to Manila
        entry_type=EntryType.SHIFT,
        start_time=start,
        end_time=end,
        crosses_midnight=crosses,
    )


def test_empty_cell():
    assert format_cell([], manila=False) == ""


def test_shift_pacific():
    assert format_cell([_shift("09:00", "17:00")], manila=False) == "09:00–17:00"


def test_shift_crosses_midnight_marker():
    assert "⏭" in format_cell([_shift("22:00", "06:00", crosses=True)],
                               manila=False)


def test_shift_manila_conversion():
    # 09:00 Pacific PDT + 15h = 00:00 next day Manila.
    cell = format_cell([_shift("09:00", "17:00")], manila=True)
    assert cell == "00:00 (+1d)–08:00 (+1d)"


def test_pto_and_uto_badges():
    pto = Entry(person_id=1, work_date="2026-07-01", entry_type=EntryType.PTO)
    uto = Entry(person_id=1, work_date="2026-07-01", entry_type=EntryType.UTO)
    assert "PTO" in format_cell([pto], manila=False)
    assert "UTO" in format_cell([uto], manila=False)
