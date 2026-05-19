"""Edit or delete an existing schedule entry.

Pick a person and a date; if something is scheduled you can change it
(same start + duration model as Add) or delete it.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from _lib import (
    entry_detail,
    get_db,
    pick_duration,
    pick_time_12h,
    require_password,
    set_flash,
    show_flash,
)
from scheduler.entries import apply_entry, delete_entries, find_conflicts
from scheduler.errors import DomainError
from scheduler.models import EntryType
from scheduler.people import list_people
from scheduler.timefmt import to_12h
from scheduler.weeks import duration_minutes, end_from_duration, iso

st.set_page_config(page_title="Edit or Delete", page_icon="✏️")
require_password()
st.title("✏️ Edit or Delete Schedule")
show_flash()

ss = st.session_state

with get_db() as conn:
    people = list_people(conn, include_inactive=True)

if not people:
    st.info("No people yet. Add someone in **Manage People**.")
    st.stop()

labels = {
    (p.name if p.is_active else f"{p.name} (inactive)"): p.id for p in people
}
chosen = st.selectbox("Person", list(labels))
person_id = labels[chosen]
the_date = st.date_input("Date", value=date.today())
date_iso = iso(the_date)

with get_db() as conn:
    found = find_conflicts(conn, [date_iso], person_id).get(date_iso, [])

if not found:
    st.info(f"Nothing scheduled for **{chosen}** on **{date_iso}**.")
    st.stop()

st.write("**Current:**")
for e in found:
    st.write(f"- {entry_detail(e)}"
             + (f" — _{e.note}_" if e.note else ""))

current = found[0]  # v1: one entry per person/date
edit_tab, delete_tab = st.tabs(["✏️ Edit", "🗑️ Delete"])

# --- Edit -----------------------------------------------------------------
with edit_tab:
    types = [t.value for t in EntryType]
    etype = st.radio(
        "Type", types, index=types.index(current.entry_type.value),
        horizontal=True, key="ed_type",
    )
    entry_type = EntryType(etype)

    start_str = end_str = None
    if entry_type is EntryType.SHIFT:
        default_start = current.start_time or "09:00"
        default_dur = (
            duration_minutes(current.start_time, current.end_time,
                             current.crosses_midnight)
            if current.entry_type is EntryType.SHIFT else 480
        )
        st.caption("Start (Pacific)")
        start_str = pick_time_12h("Hour", "ed_start", default_start)
        st.caption("Length")
        dur = pick_duration("ed_dur", default_dur)
        try:
            end_str, crosses = end_from_duration(start_str, dur)
            st.caption(f"→ Ends **{to_12h(end_str)}**"
                       + (" (next day ⏭)" if crosses else ""))
        except DomainError as exc:
            end_str = None
            st.warning(str(exc))

    note = st.text_input("Note (optional)", value=current.note or "")

    if st.button("Save changes", type="primary", key="ed_save"):
        try:
            with get_db() as conn:
                apply_entry(
                    conn, person_id, [date_iso], entry_type,
                    start_time=start_str, end_time=end_str,
                    note=note or None, overwrite=True,
                )
            set_flash(f"Updated {chosen} on {date_iso}.")
            st.rerun()
        except DomainError as exc:
            st.error(str(exc))

# --- Delete ---------------------------------------------------------------
with delete_tab:
    st.warning(
        f"Delete the schedule for **{chosen}** on **{date_iso}**? "
        "This can't be undone."
    )
    if st.button("Delete it", type="primary", key="ed_del"):
        try:
            with get_db() as conn:
                n = delete_entries(conn, person_id, [date_iso])
            set_flash(f"Deleted {n} entr{'y' if n == 1 else 'ies'} "
                      f"for {chosen} on {date_iso}.")
            st.rerun()
        except DomainError as exc:
            st.error(str(exc))
