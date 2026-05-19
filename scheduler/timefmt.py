"""Display formatting for wall-clock times.

Times are stored as 24-hour ``HH:MM`` (the canonical form). The UI shows
12-hour AM/PM — formatting only, never stored.
"""

from __future__ import annotations


def to_12h(hhmm: str) -> str:
    """``"17:05"`` → ``"5:05 PM"``; ``"00:00"`` → ``"12:00 AM"``.

    >>> to_12h("09:00")
    '9:00 AM'
    >>> to_12h("12:00")
    '12:00 PM'
    >>> to_12h("00:30")
    '12:30 AM'
    >>> to_12h("23:45")
    '11:45 PM'
    """
    h, m = (int(x) for x in hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    hour12 = h % 12 or 12
    return f"{hour12}:{m:02d} {suffix}"


def range_12h(start_hhmm: str, end_hhmm: str) -> str:
    """A shift range in 12-hour form: ``"9:00 AM–5:00 PM"``."""
    return f"{to_12h(start_hhmm)}–{to_12h(end_hhmm)}"
