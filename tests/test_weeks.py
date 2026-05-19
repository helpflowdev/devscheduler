"""Monday-anchored week math (M2)."""

from __future__ import annotations

from datetime import date

from scheduler.weeks import add_weeks, monday_of, week_dates


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
