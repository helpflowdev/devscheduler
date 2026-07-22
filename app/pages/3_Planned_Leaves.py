"""Planned Leaves — advance-filed PTO/UTO.

A durable, forward-looking leave registry. Whenever a week is built —
Copy → next week (Home) or Apply default schedule (Add Schedule) — any
planned leave overlapping that week is overlaid on top, so a leave filed
weeks ahead survives and wins over the shift the copy/template would place.
You can also apply leaves to a specific week here without re-copying.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from _lib import (
    TYPE_STYLE,
    badge,
    get_db,
    require_edit_unlock,
    require_password,
    set_flash,
    show_flash,
    theme_control,
)
from scheduler.errors import DomainError
from scheduler.leaves import (
    add_planned_leave,
    apply_planned_leaves_to_week,
    delete_planned_leave,
    leaves_overlapping,
    list_planned_leaves,
)
from scheduler.models import EntryType
from scheduler.people import list_people
from scheduler.weeks import iso, monday_of, week_dates

st.set_page_config(page_title="Planned Leaves", page_icon="🌴")
theme_control()
require_password()
st.title("🌴 Planned Leaves")
require_edit_unlock("manage planned leaves")
show_flash()

st.caption(
    "File PTO/UTO ahead of time. When you copy a week forward or apply the "
    "default schedule, any leave overlapping that week is applied "
    "automatically — overriding the shift on those days."
)


def _span(start: str, end: str) -> str:
    """Human span like 'Aug 03, 2026' or 'Aug 03 → Aug 07, 2026'."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    if s == e:
        return f"{s:%b %d, %Y}"
    if (s.month, s.year) == (e.month, e.year):
        return f"{s:%b %d} → {e:%d, %Y}"
    return f"{s:%b %d, %Y} → {e:%b %d, %Y}"


with get_db() as conn:
    people = list_people(conn)

if not people:
    st.info("No people yet — add your team in **Manage People** first.")
    st.stop()

labels = {p.name: p.id for p in people}

# ---------------------------------------------------------------------------
# File a new planned leave
# ---------------------------------------------------------------------------
with st.form("add_leave", clear_on_submit=True):
    who = st.selectbox("Person", list(labels))
    c1, c2 = st.columns(2)
    start = c1.date_input("From", value=date.today())
    end = c2.date_input("To", value=date.today())
    ltype = st.radio("Type", ["PTO", "UTO"], horizontal=True)
    note = st.text_input("Note (optional)")
    if st.form_submit_button("➕ Add planned leave", type="primary"):
        try:
            with get_db() as conn:
                lv = add_planned_leave(
                    conn, person_id=labels[who], start_date=start,
                    end_date=end, leave_type=EntryType(ltype),
                    note=note or None,
                )
            set_flash(f"Filed {ltype} for {who}: "
                      f"{_span(lv.start_date, lv.end_date)}.")
            st.rerun()
        except DomainError as exc:
            st.error(str(exc))

# ---------------------------------------------------------------------------
# Apply to an already-built week (without re-copying)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Apply to a week now")
st.caption(
    "Overlay planned leaves onto a week that's already built, without "
    "re-copying it. (Copy and the template do this for you automatically.)"
)
aw = st.date_input("Any date in the target week", value=date.today(),
                   key="apply_wk")
wk = week_dates(aw)
with get_db() as conn:
    hits = leaves_overlapping(conn, [iso(d) for d in wk])
st.write(
    f"Week of **{wk[0]:%b %d}**: "
    + (f"{len(hits)} planned leave(s) overlap this week."
       if hits else "no planned leaves overlap this week.")
)
if st.button("Apply planned leaves to this week", disabled=not hits,
             type="primary"):
    try:
        with get_db() as conn:
            written = apply_planned_leaves_to_week(conn, aw)
        set_flash(f"Applied {written} planned-leave day(s) to the week "
                  f"of {wk[0]:%b %d}.")
        st.rerun()
    except DomainError as exc:
        st.error(str(exc))

# ---------------------------------------------------------------------------
# Registry list
# ---------------------------------------------------------------------------
st.divider()
head, tog = st.columns([3, 1])
head.subheader("Filed leaves")
show_past = tog.toggle("Show past")

with get_db() as conn:
    leaves = list_planned_leaves(conn, since=None if show_past else date.today())

if not leaves:
    msg = "No planned leaves on file."
    if not show_past:
        msg += " Toggle **Show past** to include older ones."
    st.info(msg)
else:
    for lv in leaves:
        c_who, c_span, c_type, c_note, c_del = st.columns(
            [2, 2.6, 0.9, 3, 0.7])
        c_who.write(f"**{lv.person_name}**")
        c_span.write(_span(lv.start_date, lv.end_date))
        bg, fg = TYPE_STYLE[lv.leave_type.value]
        c_type.markdown(badge(lv.leave_type.value, bg, fg),
                        unsafe_allow_html=True)
        c_note.write(lv.note or "")
        if c_del.button("🗑", key=f"del_leave_{lv.id}",
                        help="Remove this planned leave from the registry"):
            with get_db() as conn:
                delete_planned_leave(conn, lv.id)
            set_flash("Removed planned leave.")
            st.rerun()
    st.caption(
        "Removing a leave here only stops it from being re-applied on "
        "future builds; any day already written to a week stays until you "
        "edit it on the schedule."
    )
