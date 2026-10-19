"""Weekly team grid — bordered rows, colored type badges, inline editing.

`format_cell` and `edit_cell_label` stay pure (plain text, used by tests).
`cell_html` adds brand-colored chips for PTO/UTO/RD. In edit mode each cell
is a popover with a small editor (replaces the old Edit/Delete page) that
can update a shift or add another beside it — a split shift (FR-10).
"""

from __future__ import annotations

import streamlit as st

from _lib import (
    TYPE_STYLE,
    badge,
    get_db,
    pick_duration_stacked,
    pick_time_12h_stacked,
)
from scheduler.coverage import week_minutes_by_person
from scheduler.entries import (
    apply_entry,
    delete_entry,
    index_by_person_date,
    update_entry,
)
from scheduler.errors import DomainError
from scheduler.models import Entry, EntryType, Person
from scheduler.timefmt import hours_label, range_12h, to_12h
from scheduler.tz import pacific_to_manila
from scheduler.weeks import DAY_NAMES, duration_minutes, end_from_duration

_EMOJI = {EntryType.PTO: "🌴", EntryType.UTO: "⚪", EntryType.RD: "💤"}

# Person · weekly hours · Mon…Sun.
_COL_WIDTHS = [1.2, 0.7] + [1] * 7
_HOURS_HELP = (
    "Total scheduled shift hours for this person this week. Split days sum "
    "both blocks; PTO/UTO/RD count as none. Recomputed on every save."
)


def _manila_12h(work_date: str, hhmm: str) -> str:
    # Show the Manila clock time as-is; the day shift is implied, no
    # "(+1d)" clutter.
    return to_12h(pacific_to_manila(work_date, hhmm).time)


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


def _badge_html(e: Entry) -> str:
    bg, fg = TYPE_STYLE[e.entry_type.value]
    return badge(f"{_EMOJI[e.entry_type]} {e.entry_type.value}", bg, fg)


def manila_cell_map(entries: list[Entry]) -> dict:
    """Re-bucket shifts onto their **Manila** day, splitting at midnight.

    A 7 AM–3 PM Pacific shift becomes 10 PM–12 AM on its day and
    12 AM–6 AM on the next day, each placed in the right Manila column.
    Whole-day RD/PTO/UTO stay on their (Pacific) work date.
    Returns {(person_id, "YYYY-MM-DD"): [html, …]}.
    """
    cells: dict = {}

    def add(pid, iso, html):
        cells.setdefault((pid, iso), []).append(html)

    for e in entries:
        if e.entry_type is not EntryType.SHIFT:
            add(e.person_id, e.work_date, _badge_html(e))
            continue
        ms = pacific_to_manila(e.work_date, e.start_time)
        me = pacific_to_manila(e.work_date, e.end_time)
        s_iso, e_iso = ms.work_date.isoformat(), me.work_date.isoformat()
        if s_iso == e_iso:
            add(e.person_id, s_iso,
                f"{to_12h(ms.time)}–{to_12h(me.time)}")
        else:  # crosses Manila midnight → split across the two days
            add(e.person_id, s_iso, f"{to_12h(ms.time)}–12:00 AM")
            add(e.person_id, e_iso, f"12:00 AM–{to_12h(me.time)}")
    return cells


def _cell_html(entries: list[Entry], manila: bool) -> str:
    parts: list[str] = []
    for e in entries:
        if e.entry_type is EntryType.SHIFT:
            parts.append(_shift_text(e, manila))
        else:
            bg, fg = TYPE_STYLE[e.entry_type.value]
            parts.append(badge(f"{_EMOJI[e.entry_type]} "
                               f"{e.entry_type.value}", bg, fg))
    # A split day stacks — two ranges side by side don't fit the column.
    return "<br>".join(parts) if parts else "—"


def edit_cell_label(entries: list[Entry], manila: bool) -> str:
    """Compact popover label for edit mode.

    One entry shows its full range; a split day shows just the start times
    ("6:00 AM + 4:00 PM") because a popover label is a single narrow line.
    """
    if not entries:
        return "✏️"
    if len(entries) == 1:
        return format_cell(entries, manila)
    parts = []
    for e in entries:
        if e.entry_type is EntryType.SHIFT:
            parts.append(_manila_12h(e.work_date, e.start_time) if manila
                         else to_12h(e.start_time))
        else:
            parts.append(e.entry_type.value)
    return " + ".join(parts)


def _slot_label(e: Entry) -> str:
    if e.entry_type is EntryType.SHIFT:
        return range_12h(e.start_time, e.end_time)
    return f"{_EMOJI[e.entry_type]} {e.entry_type.value}"


def _cell_editor(person: Person, iso: str, entries: list[Entry]) -> None:
    """Editor for one grid cell.

    The form starts from the entry being edited (9 AM · 8h on an empty
    day) and the buttons say what happens to it: **Update** changes that
    entry in place, **Add as another shift** keeps it and stacks the form's
    times beside it as a split shift (FR-10). A single "Save" here read as
    "add" to new users and silently replaced the day's shift.
    """
    st.caption(f"{person.name} · {iso}")

    current = entries[0] if entries else None
    if len(entries) > 1:
        by_id = {e.id: e for e in entries}
        current = by_id[st.radio(
            "Which shift?", list(by_id),
            format_func=lambda i: _slot_label(by_id[i]),
            key=f"sl_{person.id}_{iso}",
        )]

    _entry_form(person, iso, entries, current)


def _forget_cell(person: Person, iso: str) -> None:
    """Drop this cell's input state so the editor re-reads what was saved
    (otherwise the times just typed stay on the form)."""
    tag = f"_{person.id}_{iso}"
    for key in list(st.session_state):
        key = str(key)
        if key.startswith(("sl_", "ty_", "st_", "du_")) and tag in key:
            del st.session_state[key]


def _commit(person: Person, iso: str, verb: str, write) -> None:
    """Run one cell write, then refresh only the grid."""
    try:
        with get_db() as conn:
            write(conn)
    except DomainError as exc:
        st.error(str(exc))
        return
    _forget_cell(person, iso)
    st.session_state["_grid_toast"] = f"{verb} {person.name} · {iso}"
    st.rerun(scope="fragment")  # refresh only the grid, no flicker


def _entry_form(
    person: Person, iso: str, entries: list[Entry], current: Entry | None
) -> None:
    # Keyed by entry id, not position — adding an earlier shift reorders
    # the day, and the form must stay with the entry it was opened on.
    k = f"{person.id}_{iso}_{current.id if current else 'new'}"
    types = [t.value for t in EntryType]
    cur_type = current.entry_type.value if current else "SHIFT"
    etype = EntryType(st.radio(
        "Type", types, index=types.index(cur_type),
        horizontal=True, key=f"ty_{k}",
    ))

    start = end = None
    if etype is EntryType.SHIFT:
        d_start = (current.start_time if current
                   and current.entry_type is EntryType.SHIFT else "09:00")
        d_dur = (duration_minutes(current.start_time, current.end_time,
                                  current.crosses_midnight)
                 if current and current.entry_type is EntryType.SHIFT
                 else 480)
        start = pick_time_12h_stacked(f"st_{k}", d_start)
        dur = pick_duration_stacked(f"du_{k}", d_dur)
        try:
            end, crosses = end_from_duration(start, dur)
            st.caption(f"→ Ends {to_12h(end)}"
                       + (" (next day ⏭)" if crosses else ""))
        except DomainError as exc:
            end = None
            st.warning(str(exc))

    def add(conn):
        apply_entry(conn, person.id, [iso], etype,
                    start_time=start, end_time=end, mode="add")

    if current is None:
        if st.button("Add", type="primary", key=f"ad_{k}"):
            _commit(person, iso, "Added", add)
        return

    # A split shift can join a day of shifts, never a whole-day entry.
    can_add = etype is EntryType.SHIFT and all(
        e.entry_type is EntryType.SHIFT for e in entries)
    if can_add:
        st.caption("Change the times, then **Update** this shift or "
                   "**➕ Add** them as another shift on this day.")

    if st.button(f"Update {_slot_label(current)}", type="primary",
                 key=f"sv_{k}"):
        # In place — the day's other shift must survive the edit.
        _commit(person, iso, "Updated", lambda conn: update_entry(
            conn, current.id, etype, start_time=start, end_time=end,
            note=current.note))
    if can_add and st.button("➕ Add as another shift", key=f"ad_{k}"):
        _commit(person, iso, "Added a shift for", add)
    if st.button("Delete", key=f"dl_{k}"):
        _commit(person, iso, "Deleted",
                lambda conn: delete_entry(conn, current.id))


def render_week_grid(
    people: list[Person],
    entries: list[Entry],
    week_days,  # list[date], Mon..Sun
    *,
    manila: bool,
    edit_mode: bool = False,
) -> None:
    if st.session_state.get("_grid_toast"):
        st.toast(st.session_state.pop("_grid_toast"))

    grid = index_by_person_date(entries)
    hours = week_minutes_by_person(entries)
    # In Manila view, shifts are placed on their Manila day (split at
    # midnight); whole-day entries stay put.
    mcells = manila_cell_map(entries) if (manila and not edit_mode) else None
    tz_label = "Manila" if manila else "Pacific"

    header = st.columns(_COL_WIDTHS)
    header[0].markdown(f"**Person** · _{tz_label}_")
    header[1].markdown("**Hours**", help=_HOURS_HELP)
    for i, d in enumerate(week_days):
        header[i + 2].markdown(
            f"**{DAY_NAMES[i]}**<br>{d.strftime('%m/%d')}",
            unsafe_allow_html=True)

    for person in people:
        with st.container(border=True):  # light border per person row
            cols = st.columns(_COL_WIDTHS)
            name = (person.name if person.is_active
                    else f"{person.name} (inactive)")
            cols[0].markdown(f"**{name}**")
            cols[1].markdown(hours_label(hours.get(person.id, 0)))
            for i, d in enumerate(week_days):
                iso = d.isoformat()
                cell = grid.get((person.id, iso), [])
                if edit_mode:
                    with cols[i + 2].popover(
                        edit_cell_label(cell, manila),
                        use_container_width=True,
                    ):
                        _cell_editor(person, iso, cell)
                elif mcells is not None:
                    pieces = mcells.get((person.id, iso), [])
                    cols[i + 2].markdown(
                        "<br>".join(pieces) if pieces else "—",
                        unsafe_allow_html=True)
                else:
                    cols[i + 2].markdown(
                        _cell_html(cell, manila),
                        unsafe_allow_html=True)
