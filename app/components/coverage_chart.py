"""Weekly overlap timeline — who works when, where hours overlap."""

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


def render_overlap(
    entries: list[Entry], people: list[Person], week_days
) -> None:
    name_by_id = {p.id: p.name for p in people}
    segs = week_shift_segments(entries, name_by_id)
    if not segs:
        st.caption("No shifts this week to chart.")
        return

    label_by_date = {
        d.isoformat(): f"{DAY_NAMES[i]} {d.strftime('%m/%d')}"
        for i, d in enumerate(week_days)
    }
    day_order = list(label_by_date.values())

    df = pd.DataFrame(
        {
            "Person": s.person,
            "Day": label_by_date.get(s.work_date, s.work_date),
            "start": s.start_min,
            "end": s.end_min,
            "Shift": s.label,
        }
        for s in segs
    )

    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadius=3, opacity=0.85)
        .encode(
            x=alt.X(
                "start:Q",
                title="Time of day (Pacific)",
                scale=alt.Scale(domain=[0, 1440]),
                axis=alt.Axis(
                    values=list(range(0, 1441, 180)),
                    labelExpr=_AXIS_LABEL,
                ),
            ),
            x2="end:Q",
            y=alt.Y("Person:N", title=None),
            color=alt.Color("Person:N", legend=None),
            tooltip=["Person", "Day", "Shift"],
            row=alt.Row("Day:N", sort=day_order, title=None),
        )
        .properties(height=alt.Step(22))
    )
    st.altair_chart(chart, use_container_width=True)

    peaks = [
        f"{label_by_date[d.isoformat()]}: {peak_overlap(segs, d.isoformat())}"
        for d in week_days
        if peak_overlap(segs, d.isoformat())
    ]
    if peaks:
        st.caption("Peak people working at once — " + " · ".join(peaks))
