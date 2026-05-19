"""Team Schedule Viewer — weekly grid (US-1).

Run:  streamlit run app/Home.py
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from _lib import (  # noqa: E402  (sibling module; sets up sys.path)
    BUILD,
    get_db,
    render_conflicts,
    require_edit_unlock,
    require_password,
    saved_message,
    set_flash,
    show_flash,
    theme_control,
)
from components.coverage_chart import (  # noqa: E402
    overlap_dialog,
    render_overlap,
)
from components.week_grid import render_week_grid  # noqa: E402
from scheduler.entries import get_week_entries, get_week_people  # noqa: E402
from scheduler.errors import DomainError, OverwriteRequiredError  # noqa: E402
from scheduler.weeks import (  # noqa: E402
    add_weeks,
    copy_week,
    monday_of,
    week_dates,
)

st.set_page_config(page_title="Team Schedule Viewer", page_icon="📅",
                   layout="wide")
app_theme = theme_control()
require_password()

if "anchor" not in st.session_state:
    st.session_state.anchor = monday_of(date.today()).isoformat()

anchor = monday_of(st.session_state.anchor)

st.title("📅 Team Schedule Viewer")
show_flash()

nav_prev, nav_label, nav_next, nav_today = st.columns([1, 3, 1, 1])
if nav_prev.button("◀ Prev"):
    st.session_state.anchor = add_weeks(anchor, -1).isoformat()
    st.rerun()
if nav_next.button("Next ▶"):
    st.session_state.anchor = add_weeks(anchor, 1).isoformat()
    st.rerun()
if nav_today.button("Today"):
    st.session_state.anchor = monday_of(date.today()).isoformat()
    st.rerun()

days = week_dates(anchor)
nav_label.markdown(
    f"### Week of {days[0].strftime('%b %d')} – {days[-1].strftime('%b %d, %Y')}"
)

ctrl_jump, ctrl_tz, ctrl_edit = st.columns([2, 1, 1])
jump = ctrl_jump.date_input("Jump to date", value=anchor)
if monday_of(jump) != anchor:
    st.session_state.anchor = monday_of(jump).isoformat()
    st.rerun()
manila = ctrl_tz.toggle(
    "Manila time", help="Converts Pacific shift times per date (DST-aware).")
edit_mode = ctrl_edit.toggle(
    "✏️ Edit", help="Click any cell to add, change, or delete that day.")

st.divider()

@st.fragment
def _edit_grid(anchor_iso: str, manila: bool) -> None:
    """Edit-mode grid in its own fragment: cell clicks/saves rerun only
    this block — no whole-page flicker or scroll jump."""
    wk = week_dates(anchor_iso)
    with get_db() as conn:
        ents = get_week_entries(conn, anchor_iso)
        ppl = get_week_people(conn, anchor_iso, entries=ents)
    render_week_grid(ppl, ents, wk, manila=manila, edit_mode=True)
    if not ents:
        st.caption("No entries this week yet.")


with get_db() as conn:
    entries = get_week_entries(conn, anchor.isoformat())
    people = get_week_people(conn, anchor.isoformat(), entries=entries)

if not people:
    st.info(
        "No people yet. Add your team in **Manage People** (sidebar), "
        "then schedule them in **Add Schedule**."
    )
elif edit_mode:
    require_edit_unlock("edit schedules")
    st.caption(
        "✏️ Edit mode — click a cell to change that day. "
        "Overlap & roll-forward are hidden while editing for speed."
    )
    _edit_grid(anchor.isoformat(), manila)
else:
    render_week_grid(people, entries, days, manila=manila, edit_mode=False)
    if not entries:
        st.caption("No entries this week yet.")

    st.divider()
    ov_head, ov_btn = st.columns([4, 1])
    ov_head.subheader("Weekly overlap")
    if ov_btn.button("⤢ Expand", help="Open in a larger popup"):
        overlap_dialog(entries, people, days, app_theme)
    st.caption(
        "Each bar is a shift. Each day is boxed; bars lined up vertically "
        "within a day's box are people working at the same time. "
        "Hover a bar for its length."
    )
    render_overlap(entries, people, days, theme=app_theme)

    st.divider()
    nxt_mon = add_weeks(anchor, 1)

    def _confirm_overwrite(state_key: str, do_fn, *, show_detail: bool) -> None:
        pending = st.session_state.get(state_key)
        if not pending:
            return
        n = sum(len(v) for v in pending.values())
        st.warning(
            f"The week of {nxt_mon:%b %d} already has "
            f"{n} entr{'y' if n == 1 else 'ies'}. "
            "Overwriting clears that whole week first."
        )
        if show_detail:
            render_conflicts(pending)
        ow, cancel = st.columns([2, 1])
        if ow.button("Overwrite next week & continue", key=f"ow_{state_key}",
                     type="primary"):
            try:
                do_fn(overwrite=True)
                st.rerun()
            except DomainError as exc:
                st.error(str(exc))
        if cancel.button("Cancel", key=f"cancel_{state_key}"):
            st.session_state.pop(state_key, None)
            st.rerun()

    # Keep this schedule — exact copy into next week (FR-5).
    st.subheader("Keep this schedule")
    st.caption(
        f"Copy the week of {days[0]:%b %d} into the next week "
        f"(of {nxt_mon:%b %d}), keeping each weekday."
    )

    def _do_copy(*, overwrite: bool) -> None:
        with get_db() as conn:
            res = copy_week(conn, anchor.isoformat(), nxt_mon.isoformat(),
                            overwrite=overwrite)
        set_flash(saved_message(
            f"Copied into the week of {nxt_mon:%b %d} —",
            res.copied, res.overwritten))
        st.session_state.pop("copy_pending", None)
        st.session_state.anchor = nxt_mon.isoformat()

    if st.button("Copy this week → next week ▶", type="primary",
                 disabled=not entries):
        try:
            _do_copy(overwrite=False)
            st.rerun()
        except OverwriteRequiredError as exc:
            st.session_state.copy_pending = exc.conflicts
        except DomainError as exc:
            st.error(str(exc))

    _confirm_overwrite("copy_pending", _do_copy, show_detail=True)

st.divider()
st.caption(f"build: {BUILD}")
