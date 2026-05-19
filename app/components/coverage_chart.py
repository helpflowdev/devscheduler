"""Weekly overlap timeline — who works when, where hours overlap.

Rendered as one bordered box per day (native Streamlit container) so the
day separation is unmistakable and doesn't depend on Altair facet quirks.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from scheduler.coverage import peak_overlap, week_shift_segments
from scheduler.models import Entry, Person
from scheduler.weeks import DAY_NAMES

# Tick every 3h; label in 12-hour form (1440 == midnight next day).
_AXIS_LABEL = (
    "datum.value==1440?'12 AM':"
    "((floor(datum.value/60)%12==0?12:floor(datum.value/60)%12)"
    "+(floor(datum.value/60)<12?' AM':' PM'))"
)

# HelpFlow brand palette for bars (cycled across people).
_BRAND_RANGE = ["#2EA3F2", "#FFE4B0", "#E1E0FF", "#C3EDFF", "#A6A6A6"]

_THEMES = {
    "Dark": {"bg": "#111229", "fg": "#FFFFFF", "grid": "#2E2F52"},
    "Light": {"bg": "#FFFFFF", "fg": "#111229", "grid": "#E1E0FF"},
}


def _day_chart(rows: list[dict], theme: dict):
    df = pd.DataFrame(rows)
    return (
        alt.Chart(df)
        .mark_bar(cornerRadius=3, opacity=0.9, height=16)
        .encode(
            x=alt.X(
                "start:Q",
                title=None,
                scale=alt.Scale(domain=[0, 1440]),
                axis=alt.Axis(
                    values=list(range(0, 1441, 180)),
                    labelExpr=_AXIS_LABEL,
                ),
            ),
            x2="end:Q",
            y=alt.Y(
                "Person:N", title=None,
                axis=alt.Axis(labelLimit=140),
                sort=alt.EncodingSortField(
                    field="start", op="min", order="ascending"),
            ),
            color=alt.Color(
                "Person:N", legend=None,
                scale=alt.Scale(range=_BRAND_RANGE)),
            tooltip=["Person", "Shift"],
        )
        .properties(height=alt.Step(22))
        .configure_view(stroke=None, fill=theme["bg"])
        .configure_axis(
            labelColor=theme["fg"], titleColor=theme["fg"],
            gridColor=theme["grid"], domainColor=theme["grid"],
            tickColor=theme["grid"],
        )
        .configure(background=theme["bg"])
    )


def render_overlap(
    entries: list[Entry], people: list[Person], week_days,
    *, theme: str = "Dark",
) -> None:
    name_by_id = {p.id: p.name for p in people}
    segs = week_shift_segments(entries, name_by_id)
    if not segs:
        st.caption("No shifts this week to chart.")
        return

    th = _THEMES.get(theme, _THEMES["Dark"])
    for i, d in enumerate(week_days):
        iso = d.isoformat()
        day_label = f"{DAY_NAMES[i]} {d.strftime('%m/%d')}"
        rows = [
            {"Person": s.person, "start": s.start_min, "end": s.end_min,
             "Shift": s.label}
            for s in segs if s.work_date == iso
        ]
        with st.container(border=True):  # the per-day divider/box
            peak = peak_overlap(segs, iso)
            tag = f" · up to {peak} at once" if peak > 1 else ""
            st.markdown(f"**{day_label}**{tag}")
            if rows:
                st.altair_chart(_day_chart(rows, th), width="stretch")
            else:
                st.caption("No shifts.")
