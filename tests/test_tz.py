"""Pacific → Manila conversion (M0)."""

from __future__ import annotations

from datetime import date

from scheduler.tz import pacific_to_manila


def test_pdt_summer_offset_15h_same_day():
    # July → PDT (UTC-7); Manila UTC+8 → +15h. 08:00 + 15h = 23:00 same day.
    mt = pacific_to_manila("2026-07-01", "08:00")
    assert (mt.time, mt.day_offset) == ("23:00", 0)
    assert mt.label() == "23:00"


def test_pst_winter_offset_16h_rolls_to_next_day():
    # January → PST (UTC-8); +16h. 20:00 + 16h = 12:00 next day.
    mt = pacific_to_manila("2026-01-15", "20:00")
    assert (mt.time, mt.day_offset) == ("12:00", 1)
    assert mt.work_date == date(2026, 1, 16)
    assert mt.label() == "12:00 (+1d)"


def test_accepts_date_object():
    mt = pacific_to_manila(date(2026, 7, 1), "00:00")
    assert mt.day_offset in (0, 1)  # sanity: returns a valid conversion
