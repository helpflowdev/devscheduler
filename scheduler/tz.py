"""Pacific (base) → Manila display conversion.

Storage is always Pacific (`America/Los_Angeles`) wall-clock. Manila
(`Asia/Manila`) times are computed for display only and are never persisted.

Conversion is per-entry and uses the entry's ``work_date`` so the Pacific
DST offset is correct for that specific date (Manila is UTC+8 with no DST;
the Pacific↔Manila gap is 15h during PDT, 16h during PST).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from scheduler.config import BASE_TZ_NAME, DISPLAY_TZ_NAME

BASE_TZ = ZoneInfo(BASE_TZ_NAME)  # Pacific — source of truth
MANILA_TZ = ZoneInfo(DISPLAY_TZ_NAME)  # display only


@dataclass(slots=True, frozen=True)
class ManilaTime:
    """A Pacific time rendered in Manila.

    ``day_offset`` is the calendar-day delta vs the original Pacific date
    (Manila is ahead, so this is typically 0 or +1). Callers must surface
    it — e.g. ``08:00 (+1d)`` — rather than show the time alone.
    """

    work_date: date  # the Manila calendar date
    time: str  # "HH:MM" in Manila
    day_offset: int  # Manila date minus the source Pacific date, in days

    def label(self) -> str:
        if self.day_offset == 0:
            return self.time
        sign = "+" if self.day_offset > 0 else "-"
        return f"{self.time} ({sign}{abs(self.day_offset)}d)"


def _parse(work_date: str | date, hhmm: str) -> tuple[date, int, int]:
    d = work_date if isinstance(work_date, date) else date.fromisoformat(work_date)
    hh, mm = hhmm.split(":")
    return d, int(hh), int(mm)


@lru_cache(maxsize=1024)
def pacific_to_manila(work_date: str | date, hhmm: str) -> ManilaTime:
    """Convert a Pacific ``HH:MM`` on ``work_date`` to Manila.

    Cached: a grid render converts the same few (date, time) pairs many
    times, and the result depends only on the arguments.

    >>> pacific_to_manila("2026-07-01", "08:00").label()  # PDT (UTC-7), +15h
    '23:00'
    >>> pacific_to_manila("2026-01-15", "20:00").label()  # PST (UTC-8), +16h
    '12:00 (+1d)'
    """
    d, hh, mm = _parse(work_date, hhmm)
    pacific_dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=BASE_TZ)
    manila_dt = pacific_dt.astimezone(MANILA_TZ)
    return ManilaTime(
        work_date=manila_dt.date(),
        time=manila_dt.strftime("%H:%M"),
        day_offset=(manila_dt.date() - d).days,
    )
