"""12-hour display formatting."""

from __future__ import annotations

import pytest

from scheduler.timefmt import range_12h, to_12h


@pytest.mark.parametrize(
    "hhmm,expected",
    [
        ("00:00", "12:00 AM"),
        ("00:30", "12:30 AM"),
        ("09:00", "9:00 AM"),
        ("11:59", "11:59 AM"),
        ("12:00", "12:00 PM"),
        ("12:45", "12:45 PM"),
        ("13:05", "1:05 PM"),
        ("17:00", "5:00 PM"),
        ("23:45", "11:45 PM"),
    ],
)
def test_to_12h(hhmm, expected):
    assert to_12h(hhmm) == expected


def test_range_12h():
    assert range_12h("09:00", "17:30") == "9:00 AM–5:30 PM"
