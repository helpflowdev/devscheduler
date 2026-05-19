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
    require_password,
    saved_message,
    set_flash,
    show_flash,
)
from components.coverage_chart import render_overlap  # noqa: E402
from components.week_grid import render_week_grid  # noqa: E402
from scheduler.entries import get_week_entries, get_week_people  # noqa: E402
from scheduler.errors import DomainError, OverwriteRequiredError  # noqa: E402
from scheduler.weeks import (  # noqa: E402
    add_weeks,
    copy_week,
    copy_week_with_offset,
    monday_of,
    preview_offset,
    week_dates,
)

st.set_page_config(page_title="Team Schedule Viewer", page_icon="📅",
                   layout="wide")
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

ctrl_jump, ctrl_tz = st.columns([2, 2])
jump = ctrl_jump.date_input("Jump to date", value=anchor)
if monday_of(jump) != anchor:
    st.session_state.anchor = monday_of(jump).isoformat()
    st.rerun()
manila = ctrl_tz.toggle(
    "Show Manila time", help="Converts Pacific shift times per date (DST-aware)."
)

st.divider()

with get_db() as conn:
    entries = get_week_entries(conn, anchor.isoformat())
    people = get_week_people(conn, anchor.isoformat(), entries=entries)

if not people:
    st.info(
        "No people yet. Add your team in **Manage People** (sidebar), "
        "then schedule them in **Add Schedule**."
    )
else:
    render_week_grid(people, entries, days, manila=manila)
    if not entries:
        st.caption("No entries this week yet.")

    st.divider()
    head, appear = st.columns([3, 1])
    head.subheader("Weekly overlap")
    chart_theme = appear.radio(
        "Appearance", ["Dark", "Light"], horizontal=True,
        label_visibility="collapsed",
    )
    st.caption(
        "Each bar is a shift. Each day is boxed; bars lined up vertically "
        "within a day's box are people working at the same time."
    )
    render_overlap(entries, people, days, theme=chart_theme)

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

    # Adjust next week — slide every shift by an offset (FR-6).
    with st.expander("Adjust next week — slide all shifts by an offset"):
        st.caption(
            "Copies this week into the week of "
            f"{nxt_mon:%b %d} with every **shift** moved by the offset. "
            "PTO/UTO are copied unchanged."
        )
        c_dir, c_h, c_m = st.columns(3)
        direction = c_dir.radio("Direction", ["Later (+)", "Earlier (−)"])
        off_h = c_h.number_input("Hours", min_value=0, max_value=23, value=1)
        off_m = c_m.number_input("Minutes", min_value=0, max_value=59,
                                 value=0, step=5)
        sign = 1 if direction.startswith("Later") else -1
        offset_min = sign * (int(off_h) * 60 + int(off_m))

        if st.button("Preview", disabled=not entries):
            if offset_min == 0:
                st.error("Offset is zero — use the exact copy above.")
            else:
                with get_db() as conn:
                    st.session_state.offset_preview = (
                        offset_min,
                        preview_offset(conn, anchor.isoformat(),
                                       nxt_mon.isoformat(), offset_min),
                    )

        prev = st.session_state.get("offset_preview")
        if prev and prev[0] == offset_min:
            _, rows = prev
            label = (f"+{off_h}h{int(off_m):02d}" if sign > 0
                     else f"−{off_h}h{int(off_m):02d}")
            st.write(f"**Preview** (offset {label}) → week of "
                     f"{nxt_mon:%b %d}:")
            st.dataframe(
                [
                    {
                        "Person": r.person_name,
                        "Date": r.dst_date,
                        "Type": r.entry_type,
                        "Was": r.old or "—",
                        "Becomes": r.new or "(unchanged)",
                    }
                    for r in rows
                ],
                width="stretch", hide_index=True,
            )

            def _do_offset(*, overwrite: bool) -> None:
                with get_db() as conn:
                    res = copy_week_with_offset(
                        conn, anchor.isoformat(), nxt_mon.isoformat(),
                        offset_min, overwrite=overwrite)
                set_flash(saved_message(
                    f"Applied offset → week of {nxt_mon:%b %d} —",
                    res.copied, res.overwritten))
                for k in ("offset_preview", "offset_pending"):
                    st.session_state.pop(k, None)
                st.session_state.anchor = nxt_mon.isoformat()

            if st.button("Apply offset copy", type="primary"):
                try:
                    _do_offset(overwrite=False)
                    st.rerun()
                except OverwriteRequiredError as exc:
                    st.session_state.offset_pending = exc.conflicts
                except DomainError as exc:
                    st.error(str(exc))

            _confirm_overwrite("offset_pending", _do_offset, show_detail=False)

st.divider()
st.caption(f"build: {BUILD}")
