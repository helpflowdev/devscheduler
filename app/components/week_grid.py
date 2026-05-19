"""Weekly team grid rendering (US-1).

Formatting (`format_cell`) is pure and import-safe; `render_week_grid`
does the Streamlit layout.
"""

from __future__ import annotations

import streamlit as st

from scheduler.entries import index_by_person_date
from scheduler.models import Entry, EntryType, Person
from scheduler.timefmt import range_12h, to_12h
from scheduler.tz import pacific_to_manila
from scheduler.weeks import DAY_NAMES

_BADGES = {
    EntryType.PTO: "🌴 PTO",
    EntryType.UTO: "⚪ UTO",
    EntryType.RD: "💤 RD",
}


def _manila_12h(work_date: str, hhmm: str) -> str:
    mt = pacific_to_manila(work_date, hhmm)
    off = "" if mt.day_offset == 0 else f" ({'+' if mt.day_offset > 0 else '-'}"\
        f"{abs(mt.day_offset)}d)"
    return to_12h(mt.time) + off


def _shift_text(e: Entry, manila: bool) -> str:
    if not manila:
        body = range_12h(e.start_time, e.end_time)
    else:
        body = (f"{_manila_12h(e.work_date, e.start_time)}–"
                f"{_manila_12h(e.work_date, e.end_time)}")
    # ⏭ flags a shift that crosses midnight (distinct from the Manila
    # day-offset, which the label already shows as "(+1d)").
    return f"{body} ⏭" if e.crosses_midnight else body


def format_cell(entries: list[Entry], manila: bool) -> str:
    """One grid cell. Empty string when nothing is scheduled."""
    parts: list[str] = []
    for e in entries:
        if e.entry_type is EntryType.SHIFT:
            parts.append(_shift_text(e, manila))
        else:
            parts.append(_BADGES[e.entry_type])
    return "  ·  ".join(parts)


def render_week_grid(
    people: list[Person],
    entries: list[Entry],
    week_days,  # list[date], Mon..Sun
    *,
    manila: bool,
) -> None:
    grid = index_by_person_date(entries)
    tz_label = "Manila" if manila else "Pacific"

    header = st.columns([2] + [1] * 7)
    header[0].markdown(f"**Person** · _{tz_label}_")
    for i, d in enumerate(week_days):
        header[i + 1].markdown(f"**{DAY_NAMES[i]}**<br>{d.strftime('%m/%d')}",
                               unsafe_allow_html=True)

    for person in people:
        cols = st.columns([2] + [1] * 7)
        name = person.name if person.is_active else f"{person.name} (inactive)"
        cols[0].write(name)
        for i, d in enumerate(week_days):
            cell = format_cell(grid.get((person.id, d.isoformat()), []), manila)
            cols[i + 1].write(cell if cell else "—")
