"""Add schedule (US-2, US-3).

Step 1 — pick a person and the date(s)/week.
Step 2 — pick the type (Shift / PTO / UTO / RD) and, for shifts, the times.
(Per-entry editing/deleting is inline on Home — toggle Edit there.)

Bulk-applies one entry to every selected date; existing entries on those
dates are listed and require an explicit overwrite confirm (FR-3, FR-4).
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from _lib import (
    get_db,
    pick_duration,
    pick_time_12h,
    render_conflicts,
    require_password,
    saved_message,
    set_flash,
    show_flash,
)
from scheduler.entries import apply_entry
from scheduler.errors import DomainError, OverwriteRequiredError
from scheduler.models import EntryType
from scheduler.people import add_person, list_people
from scheduler.timefmt import to_12h
from scheduler.weeks import DAY_NAMES, end_from_duration, iso, week_dates

st.set_page_config(page_title="Add Schedule", page_icon="📝")
require_password()
st.title("📝 Add Schedule")
show_flash()

ss = st.session_state
ss.setdefault("ae_step", 1)
ss.setdefault("ae_person_id", None)
ss.setdefault("ae_person_name", "")
ss.setdefault("ae_dates", [])
ss.setdefault("ae_pending", None)  # holds inputs awaiting overwrite confirm


def _reset() -> None:
    for k in ("ae_step", "ae_person_id", "ae_person_name", "ae_dates",
              "ae_pending"):
        ss.pop(k, None)
    ss.ae_step = 1


# ======================================================================
# Step 1 — person + dates
# ======================================================================
if ss.ae_step == 1:
    with get_db() as conn:
        people = list_people(conn)

    if people:
        labels = {p.name: p.id for p in people}
        chosen = st.selectbox("Person", list(labels))
        ss.ae_person_id = labels[chosen]
        ss.ae_person_name = chosen
    else:
        st.info("No people yet — add the first one below.")

    with st.expander("➕ Add a new person"):
        new_name = st.text_input("New person name", key="ae_new_name")
        if st.button("Add person"):
            try:
                with get_db() as conn:
                    p = add_person(conn, new_name)
                set_flash(f"Added {p.name}.")
                st.rerun()
            except DomainError as exc:
                st.error(str(exc))

    st.divider()
    mode = st.radio(
        "Dates",
        ["Single date", "Whole week", "Pick days in a week"],
        horizontal=True,
    )

    if mode == "Single date":
        d = st.date_input("Date", value=date.today())
        ss.ae_dates = [iso(d)]
    elif mode == "Whole week":
        anchor = st.date_input("Any date in the week", value=date.today())
        wk = week_dates(anchor)
        ss.ae_dates = [iso(x) for x in wk]
        st.caption(f"Mon {wk[0]:%m/%d} → Sun {wk[-1]:%m/%d} (7 days)")
    else:  # Pick days in a week
        anchor = st.date_input("Any date in the week", value=date.today())
        wk = week_dates(anchor)
        picks = st.multiselect(
            "Which days?",
            options=list(range(7)),
            format_func=lambda i: f"{DAY_NAMES[i]} {wk[i]:%m/%d}",
        )
        ss.ae_dates = [iso(wk[i]) for i in sorted(picks)]

    st.write(f"**Selected:** {len(ss.ae_dates)} date(s)")
    can_next = bool(ss.ae_person_id) and bool(ss.ae_dates)
    if st.button("Next ▶", disabled=not can_next, type="primary"):
        ss.ae_step = 2
        ss.ae_pending = None
        st.rerun()

# ======================================================================
# Step 2 — type + time
# ======================================================================
else:
    st.markdown(
        f"**{ss.ae_person_name}** · {len(ss.ae_dates)} date(s): "
        f"{', '.join(ss.ae_dates)}"
    )

    etype = st.radio("Type", [e.value for e in EntryType], horizontal=True)
    entry_type = EntryType(etype)

    start_str = end_str = None
    if entry_type is EntryType.SHIFT:
        st.caption("Start (Pacific)")
        start_str = pick_time_12h("Hour", "ae_start", "09:00")
        st.caption("Length")
        dur = pick_duration("ae_dur", 480)
        try:
            end_str, crosses = end_from_duration(start_str, dur)
            st.caption(
                f"→ Ends **{to_12h(end_str)}**"
                + (" (next day ⏭)" if crosses else "")
            )
        except DomainError as exc:
            end_str = None
            st.warning(str(exc))
    note = st.text_input("Note (optional)")

    nav_back, nav_save = st.columns([1, 2])
    if nav_back.button("◀ Back"):
        ss.ae_step = 1
        ss.ae_pending = None
        st.rerun()

    def _do_apply(overwrite: bool) -> None:
        with get_db() as conn:
            res = apply_entry(
                conn, ss.ae_person_id, ss.ae_dates, entry_type,
                start_time=start_str, end_time=end_str,
                note=note or None, overwrite=overwrite,
            )
        set_flash(saved_message("Saved", res.created, res.overwritten))
        _reset()

    if nav_save.button("Save", type="primary"):
        try:
            _do_apply(overwrite=False)
            st.rerun()
        except OverwriteRequiredError as exc:
            ss.ae_pending = exc.conflicts
        except DomainError as exc:
            st.error(str(exc))

    if ss.ae_pending:
        st.warning("⚠️ These dates already have entries:")
        render_conflicts(ss.ae_pending)
        if st.button("Overwrite & Save", type="primary"):
            try:
                _do_apply(overwrite=True)
                st.rerun()
            except DomainError as exc:
                st.error(str(exc))
