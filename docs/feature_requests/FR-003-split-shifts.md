# Feature Request — Split shifts + weekly hours total

**Submitted by:** Team lead
**Date:** 2026-08-24
**Status:** Delivered — `mode="add"` on `apply_entry`, per-entry edit/delete,
multi-slot cell editor, weekly Hours column (PRD FR-10 / FR-11)

---

## User story

As a scheduler I want to put **two shifts on one day** for the same person,
so that split schedules (e.g. 6:00–10:00 AM and 4:00–8:00 PM) can be
recorded as they actually are, instead of one block that hides the gap.

Follow-on ask in the same conversation: **show each person's total hours
for the week beside their name**, so a split day's real load is visible at a
glance rather than inferred from the cells.

## Context

- v1 deliberately enforced **one entry per `(person_id, work_date)`** in app
  logic: an apply deletes the existing rows for that pair and inserts
  (PRD FR-2/FR-4). Saving a second shift on a day silently replaced the
  first.
- The *schema* was left open for this from the start — there is no
  `UNIQUE(person_id, work_date)` (DATA_MODEL "Constraints"), and the read
  path already handles a list per cell (`index_by_person_date`,
  `format_cell`, `manila_cell_map`, `week_shift_segments`). Only the write
  path and the cell editor assumed one.

## Behaviour

- **Two apply modes** on `apply_entry`:
  - `mode="replace"` (default) — unchanged v1 behaviour: existing entries on
    the target dates raise `OverwriteRequiredError` unless `overwrite=True`,
    which deletes then inserts.
  - `mode="add"` — insert **alongside** what the day already holds. No
    overwrite prompt; instead the day's composition is validated.
- **Day composition rules** (`check_day_composition`, pure/testable):
  - A day may hold any number of `SHIFT` entries as long as none **overlap**.
    Touching blocks (09:00–13:00 + 13:00–17:00) are allowed.
  - `PTO`/`UTO`/`RD` are **whole-day and exclusive** — they can neither be
    added to a day that has entries, nor joined by a shift. Changing such a
    day means replacing it.
  - Overnight shifts are compared on a 0–2880 minute line, so 22:00–06:00
    and 06:00–10:00 on the same date do not falsely collide.
  - Every target date is validated **before** anything is written — a bad
    date in a bulk apply fails the whole apply, no partial writes.
- **Per-entry edit and delete:** `update_entry(entry_id, …)` edits one entry
  in place (validated against that day's *other* entries, note preserved)
  and `delete_entry(entry_id)` removes just that one. The grid's cell editor
  is now a slot picker — one slot per existing entry plus "➕ Add a shift"
  when the day holds only shifts.
- **Templates** may list several rows for the same `(person, weekday)`: the
  first row for a cell replaces it, the rest are added alongside.
- **Week builders are unaffected by design:** copy-forward wipes the whole
  destination week and re-inserts every source row, so split days carry
  forward as-is; the planned-leave overlay deletes by `(person, date)`, so a
  leave still wins over *both* halves of a split day.

### Weekly hours column

- The grid gains an **Hours** column between *Person* and *Mon*, showing that
  person's total scheduled SHIFT time for the displayed week
  (`week_minutes_by_person`, pure, in `scheduler/coverage.py`).
- A split day sums its blocks; an overnight shift counts its full length;
  PTO/UTO/RD carry no hours.
- **No compute button is needed** — it recomputes on every render. The
  edit-mode grid is a Streamlit fragment that re-reads the week from the DB
  on each rerun, and every cell save/delete triggers that rerun, so the
  total moves the moment an entry changes.
- The figure is timezone-independent (a shift is the same length in Pacific
  and Manila), so one total serves both views. Note it is bucketed by
  **Pacific `work_date`**, matching how entries are stored.

## Definition of Done

- A second shift can be added to a day from both the Add Schedule page
  ("Add a second shift") and the inline grid cell editor, and each entry can
  be edited or deleted independently.
- Overlapping shifts and whole-day/shift mixes are rejected with a
  user-readable message.
- The viewer stacks a split day's entries in the cell (Pacific and Manila
  views); the coverage timeline draws one bar per shift.
- Each row shows the week's total scheduled hours beside the name, updating
  without an explicit recompute step.
- Business logic stays in `scheduler/` with tests covering the composition
  rules, add mode, per-entry update/delete, template split rows,
  copy-forward, and the leave overlay.

## Out of scope

- **Cross-date overlap:** an overnight shift on Mon (22:00–06:00) is not
  checked against Tue's early shift. Each date is validated on its own.
- Automatic gap/break calculation, minimum-rest rules, or total-hours caps
  per person per day.
- **Actual (worked) hours** — the tool knows only what is scheduled; there is
  no time-tracking integration, so the Hours column is a plan, not a
  timesheet.
- Per-day hour subtotals or a team-wide weekly total row.
- A dedicated "split shift" entry type — a split day is simply two SHIFT
  rows.
