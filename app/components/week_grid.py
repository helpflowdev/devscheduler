"""Weekly team grid — bordered rows, colored type badges, inline editing.

`format_cell` stays pure (returns plain text, used by tests). `cell_html`
adds brand-colored chips for PTO/UTO/RD. In edit mode each cell is a
popover with a small editor (replaces the old Edit/Delete page).
"""

from __future__ import annotations

import streamlit as st

from _lib import (
    TYPE_STYLE,
    badge,
    get_db,
    pick_duration_stacked,
    pick_time_12h_stacked,
    set_flash,
)
from scheduler.entries import apply_entry, delete_entries, index_by_person_date
from scheduler.errors import DomainError
from scheduler.models import Entry, EntryType, Person
from scheduler.timefmt import range_12h, to_12h
from scheduler.tz import pacific_to_manila
from scheduler.weeks import DAY_NAMES, duration_minutes, end_from_duration

_EMOJI = {EntryType.PTO: "🌴", EntryType.UTO: "⚪", EntryType.RD: "💤"}


def _manila_12h(work_date: str, hhmm: str) -> str:
    mt = pacific_to_manila(work_date, hhmm)
    off = "" if mt.day_offset == 0 else (
        f" ({'+' if mt.day_offset > 0 else '-'}{abs(mt.day_offset)}d)")
    return to_12h(mt.time) + off


def _shift_text(e: Entry, manila: bool) -> str:
    if not manila:
        body = range_12h(e.start_time, e.end_time)
    else:
        body = (f"{_manila_12h(e.work_date, e.start_time)}–"
                f"{_manila_12h(e.work_date, e.end_time)}")
    return f"{body} ⏭" if e.crosses_midnight else body


def format_cell(entries: list[Entry], manila: bool) -> str:
    """Plain-text cell (kept for tests / popover labels)."""
    parts: list[str] = []
    for e in entries:
        if e.entry_type is EntryType.SHIFT:
            parts.append(_shift_text(e, manila))
        else:
            parts.append(f"{_EMOJI[e.entry_type]} {e.entry_type.value}")
    return "  ·  ".join(parts)


def _cell_html(entries: list[Entry], manila: bool) -> str:
    parts: list[str] = []
    for e in entries:
        if e.entry_type is EntryType.SHIFT:
            parts.append(_shift_text(e, manila))
        else:
            bg, fg = TYPE_STYLE[e.entry_type.value]
            parts.append(badge(f"{_EMOJI[e.entry_type]} "
                               f"{e.entry_type.value}", bg, fg))
    return " · ".join(parts) if parts else "—"


def _cell_editor(person: Person, iso: str, current: Entry | None) -> None:
    st.caption(f"{person.name} · {iso}")
    types = [t.value for t in EntryType]
    cur_type = current.entry_type.value if current else "SHIFT"
    etype = EntryType(st.radio(
        "Type", types, index=types.index(cur_type),
        horizontal=True, key=f"ty_{person.id}_{iso}",
    ))

    start = end = None
    if etype is EntryType.SHIFT:
        d_start = (current.start_time if current
                   and current.entry_type is EntryType.SHIFT else "09:00")
        d_dur = (duration_minutes(current.start_time, current.end_time,
                                  current.crosses_midnight)
                 if current and current.entry_type is EntryType.SHIFT
                 else 480)
        start = pick_time_12h_stacked(f"st_{person.id}_{iso}", d_start)
        dur = pick_duration_stacked(f"du_{person.id}_{iso}", d_dur)
        try:
            end, crosses = end_from_duration(start, dur)
            st.caption(f"→ Ends {to_12h(end)}"
                       + (" (next day ⏭)" if crosses else ""))
        except DomainError as exc:
            end = None
            st.warning(str(exc))

    if st.button("Save", type="primary", key=f"sv_{person.id}_{iso}"):
        try:
            with get_db() as conn:
                apply_entry(conn, person.id, [iso], etype,
                            start_time=start, end_time=end, overwrite=True)
            set_flash(f"Saved {person.name} · {iso}.")
            st.rerun()
        except DomainError as exc:
            st.error(str(exc))

    if current and st.button("Delete", key=f"dl_{person.id}_{iso}"):
        try:
            with get_db() as conn:
                delete_entries(conn, person.id, [iso])
            set_flash(f"Deleted {person.name} · {iso}.")
            st.rerun()
        except DomainError as exc:
            st.error(str(exc))


def render_week_grid(
    people: list[Person],
    entries: list[Entry],
    week_days,  # list[date], Mon..Sun
    *,
    manila: bool,
    edit_mode: bool = False,
) -> None:
    grid = index_by_person_date(entries)
    tz_label = "Manila" if manila else "Pacific"

    header = st.columns([2] + [1] * 7)
    header[0].markdown(f"**Person** · _{tz_label}_")
    for i, d in enumerate(week_days):
        header[i + 1].markdown(
            f"**{DAY_NAMES[i]}**<br>{d.strftime('%m/%d')}",
            unsafe_allow_html=True)

    for person in people:
        with st.container(border=True):  # light border per person row
            cols = st.columns([2] + [1] * 7)
            name = (person.name if person.is_active
                    else f"{person.name} (inactive)")
            cols[0].markdown(f"**{name}**")
            for i, d in enumerate(week_days):
                iso = d.isoformat()
                cell = grid.get((person.id, iso), [])
                if edit_mode:
                    label = format_cell(cell, manila) or "✏️"
                    with cols[i + 1].popover(label,
                                             use_container_width=True):
                        _cell_editor(person, iso,
                                     cell[0] if cell else None)
                else:
                    cols[i + 1].markdown(
                        _cell_html(cell, manila),
                        unsafe_allow_html=True)
