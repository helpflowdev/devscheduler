"""Weekly shift segments + overlap counting."""

from __future__ import annotations

from scheduler.coverage import peak_overlap, week_shift_segments
from scheduler.models import Entry, EntryType

NAMES = {1: "Alice", 2: "Bob"}


def _shift(pid, d, s, e, crosses=False):
    return Entry(person_id=pid, work_date=d, entry_type=EntryType.SHIFT,
                 start_time=s, end_time=e, crosses_midnight=crosses)


def test_plain_shift_one_segment():
    segs = week_shift_segments([_shift(1, "2026-05-18", "09:00", "17:00")],
                               NAMES)
    assert len(segs) == 1
    s = segs[0]
    assert (s.person, s.start_min, s.end_min) == ("Alice", 540, 1020)
    assert s.label == "9:00 AM–5:00 PM"


def test_overnight_splits_into_two_segments():
    segs = week_shift_segments(
        [_shift(1, "2026-05-18", "22:00", "02:00", crosses=True)], NAMES)
    spans = sorted((s.start_min, s.end_min) for s in segs)
    assert spans == [(0, 120), (1320, 1440)]
    assert all(s.label == "10:00 PM–2:00 AM" for s in segs)


def test_non_shift_entries_ignored():
    e = Entry(person_id=1, work_date="2026-05-18", entry_type=EntryType.RD)
    assert week_shift_segments([e], NAMES) == []


def test_peak_overlap_counts_concurrency():
    segs = week_shift_segments(
        [
            _shift(1, "2026-05-18", "09:00", "17:00"),
            _shift(2, "2026-05-18", "12:00", "20:00"),  # overlaps 12–17
        ],
        NAMES,
    )
    assert peak_overlap(segs, "2026-05-18") == 2
    assert peak_overlap(segs, "2026-05-19") == 0


def test_back_to_back_is_not_overlap():
    segs = week_shift_segments(
        [
            _shift(1, "2026-05-18", "09:00", "12:00"),
            _shift(2, "2026-05-18", "12:00", "17:00"),  # touches, no overlap
        ],
        NAMES,
    )
    assert peak_overlap(segs, "2026-05-18") == 1
