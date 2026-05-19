"""Monday-anchored week math (M2)."""

from __future__ import annotations

from datetime import date

import pytest

from scheduler.errors import ValidationError
from scheduler.weeks import (
    add_weeks,
    duration_minutes,
    end_from_duration,
    monday_of,
    week_dates,
)


def test_end_from_duration_same_day():
    assert end_from_duration("09:00", 8 * 60) == ("17:00", False)


def test_end_from_duration_crosses_midnight():
    assert end_from_duration("22:00", 4 * 60) == ("02:00", True)


def test_end_from_duration_ends_exactly_midnight():
    assert end_from_duration("16:00", 8 * 60) == ("00:00", True)


@pytest.mark.parametrize("bad", [0, -30, 24 * 60, 30 * 60])
def test_end_from_duration_rejects_bad_length(bad):
    with pytest.raises(ValidationError):
        end_from_duration("09:00", bad)


def test_duration_minutes_roundtrip():
    for start, dur in (("09:00", 480), ("22:00", 240), ("16:00", 480)):
        end, crosses = end_from_duration(start, dur)
        assert duration_minutes(start, end, crosses) == dur


def test_monday_of_midweek():
    # 2026-05-13 is a Wednesday → Monday is 2026-05-11.
    assert monday_of("2026-05-13") == date(2026, 5, 11)


def test_monday_of_when_already_monday():
    assert monday_of(date(2026, 5, 11)) == date(2026, 5, 11)


def test_monday_of_sunday_stays_in_same_week():
    # 2026-05-17 is a Sunday → still the week starting 2026-05-11.
    assert monday_of("2026-05-17") == date(2026, 5, 11)


def test_week_dates_is_mon_to_sun():
    days = week_dates("2026-05-14")
    assert days[0] == date(2026, 5, 11) and days[-1] == date(2026, 5, 17)
    assert len(days) == 7


def test_add_weeks_returns_monday_anchor():
    assert add_weeks("2026-05-13", 1) == date(2026, 5, 18)
    assert add_weeks("2026-05-13", -2) == date(2026, 4, 27)
