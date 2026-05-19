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


def test_shift_pacific_12h():
    assert format_cell([_shift("09:00", "17:00")],
                       manila=False) == "9:00 AM–5:00 PM"


def test_shift_crosses_midnight_marker():
    assert "⏭" in format_cell([_shift("22:00", "06:00", crosses=True)],
                               manila=False)


def test_shift_manila_conversion_12h():
    # 09:00 Pacific PDT + 15h = 00:00 next day Manila; 17:00 → 08:00 (+1d).
    cell = format_cell([_shift("09:00", "17:00")], manila=True)
    assert cell == "12:00 AM (+1d)–8:00 AM (+1d)"


def test_badges_pto_uto_rd():
    for et, tag in (
        (EntryType.PTO, "PTO"),
        (EntryType.UTO, "UTO"),
        (EntryType.RD, "RD"),
    ):
        e = Entry(person_id=1, work_date="2026-07-01", entry_type=et)
        assert tag in format_cell([e], manila=False)
