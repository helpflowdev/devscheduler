"""Reusable weekly templates.

The default roster lives in code (not the DB) so a Streamlit-Cloud reboot
that wipes the ephemeral SQLite can't lose it — applying the template
rebuilds the people and the whole week, then you tweak exceptions.
"""

from __future__ import annotations

from datetime import timedelta

from scheduler.db import Connection
from scheduler.entries import apply_entry
from scheduler.models import EntryType
from scheduler.people import add_person
from scheduler.weeks import iso, monday_of

# Each row: (person, weekday 0=Mon..6=Sun, type, start, end).
# Times are Pacific "HH:MM"; None for whole-day RD/PTO/UTO.
_S, _RD = "SHIFT", "RD"
DEFAULT_TEMPLATE: list[tuple[str, int, str, str | None, str | None]] = []


def _week(name: str, days: dict[int, tuple[str, str | None, str | None]]):
    for wd, (etype, s, e) in days.items():
        DEFAULT_TEMPLATE.append((name, wd, etype, s, e))


# JC — 7:00 AM–3:00 PM Mon–Fri, RD Sat/Sun
_week("JC", {**{d: (_S, "07:00", "15:00") for d in range(5)},
             5: (_RD, None, None), 6: (_RD, None, None)})
# Gio — RD Mon, 11:00 AM–7:30 PM Tue–Fri, RD Sat, 9:00 AM–5:00 PM Sun
_week("Gio", {0: (_RD, None, None),
              **{d: (_S, "11:00", "19:30") for d in (1, 2, 3, 4)},
              5: (_RD, None, None), 6: (_S, "09:00", "17:00")})
# Karim — RD Mon, 12–8 Tue–Fri, 9–5 Sat, 12–8 Sun
_week("Karim", {0: (_RD, None, None),
                **{d: (_S, "12:00", "20:00") for d in (1, 2, 3, 4)},
                5: (_S, "09:00", "17:00"), 6: (_S, "12:00", "20:00")})
# Shierraine — 2–10 Mon–Thu, RD Fri/Sat, 2–10 Sun
_week("Shierraine", {**{d: (_S, "14:00", "22:00") for d in range(4)},
                     4: (_RD, None, None), 5: (_RD, None, None),
                     6: (_S, "14:00", "22:00")})
# Marion — RD Mon/Tue, 3:30 PM–12:00 AM Wed–Fri, RD Sat/Sun
_week("Marion", {0: (_RD, None, None), 1: (_RD, None, None),
                 **{d: (_S, "15:30", "00:00") for d in (2, 3, 4)},
                 5: (_RD, None, None), 6: (_RD, None, None)})


def ensure_person(conn: Connection, name: str) -> int:
    """Return the active person's id, creating them if missing."""
    row = conn.execute(
        "SELECT id FROM person WHERE is_active = 1 "
        "AND lower(name) = lower(?)",
        (name,),
    ).fetchone()
    if row:
        return row["id"]
    return add_person(conn, name).id


def apply_template(
    conn: Connection,
    any_date_in_week,
    template=DEFAULT_TEMPLATE,
) -> int:
    """Write ``template`` onto the week containing ``any_date_in_week``.

    Missing people are created. Existing entries on the affected
    person/dates are overwritten. Returns the number of entries written.
    """
    mon = monday_of(any_date_in_week)
    ids: dict[str, int] = {}
    n = 0
    for name, wd, etype, start, end in template:
        pid = ids.get(name) or ids.setdefault(name, ensure_person(conn, name))
        apply_entry(
            conn, pid, [iso(mon + timedelta(days=wd))],
            EntryType(etype), start_time=start, end_time=end,
            overwrite=True,
        )
        n += 1
    return n
