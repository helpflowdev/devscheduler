"""Weekly shift-coverage logic for the overlap view (pure, testable).

Turns SHIFT entries into time segments per day so the UI can draw a
timeline and show where people's hours overlap. PTO/UTO/RD have no hours,
so they produce no segments.
"""

from __future__ import annotations

from dataclasses import dataclass

from scheduler.models import Entry, EntryType
from scheduler.timefmt import hours_label, range_12h
from scheduler.weeks import duration_minutes


def _to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _length_label(start_min: int, end_min: int) -> str:
    """Whole-shift duration as e.g. ``"8h"`` or ``"7h 30m"``."""
    dur = end_min - start_min
    if dur <= 0:
        dur += 24 * 60
    return hours_label(dur)


@dataclass(slots=True)
class Segment:
    person: str
    work_date: str          # the day the segment is drawn on (YYYY-MM-DD)
    start_min: int          # minutes from midnight, 0..1440
    end_min: int            # > start_min
    label: str              # 12-hour range of the *whole* shift
    length: str = ""        # whole-shift duration, e.g. "8h"


def week_shift_segments(
    entries: list[Entry], name_by_id: dict[int, str]
) -> list[Segment]:
    """One or two segments per SHIFT (two if it crosses midnight).

    An overnight shift (e.g. 22:00–02:00) is split into ``[22:00, 24:00]``
    on its own day plus ``[00:00, 02:00]`` on the same day's row, so the
    early-morning coverage is visible alongside everyone else's.
    """
    segs: list[Segment] = []
    for e in entries:
        if e.entry_type is not EntryType.SHIFT:
            continue
        person = name_by_id.get(e.person_id, f"#{e.person_id}")
        s, t = _to_min(e.start_time), _to_min(e.end_time)
        label = range_12h(e.start_time, e.end_time)
        length = _length_label(s, t)
        if e.crosses_midnight or t <= s:
            segs.append(Segment(person, e.work_date, s, 1440, label, length))
            if t > 0:
                segs.append(Segment(person, e.work_date, 0, t, label, length))
        else:
            segs.append(Segment(person, e.work_date, s, t, label, length))
    return segs


def peak_overlap(segments: list[Segment], work_date: str) -> int:
    """Max number of people working at the same instant on ``work_date``."""
    events: list[tuple[int, int]] = []
    for sg in segments:
        if sg.work_date == work_date:
            events.append((sg.start_min, 1))
            events.append((sg.end_min, -1))
    events.sort(key=lambda x: (x[0], x[1]))  # ends before starts at a tie
    cur = peak = 0
    for _, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


def week_minutes_by_person(entries: list[Entry]) -> dict[int, int]:
    """Total scheduled SHIFT minutes per ``person_id`` across ``entries``.

    A split day sums its blocks; PTO/UTO/RD carry no hours and contribute
    nothing. The figure is timezone-independent — a shift is the same
    length in Pacific and Manila — so the same total serves both views.
    """
    totals: dict[int, int] = {}
    for e in entries:
        if e.entry_type is not EntryType.SHIFT:
            continue
        totals[e.person_id] = totals.get(e.person_id, 0) + duration_minutes(
            e.start_time, e.end_time, e.crosses_midnight
        )
    return totals
