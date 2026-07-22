# Feature Request — Planned Leaves (advance PTO/UTO)

**Submitted by:** Team lead
**Date:** 2026-07-21
**Status:** Delivered — schema v4, `scheduler/leaves.py`, page 3

---

## User story

As a team lead, I want a page to record PTO/UTO in advance, so that when I
duplicate a week forward or apply the default template, those already-filed
leaves are taken into account instead of being buried under a copied shift.
This covers leave filed two weeks ahead or more.

## Context

- Leaves are often filed well before the week they fall in is built. The
  week-building tools (copy-forward, apply-default-template) overwrite the
  destination week, so a leave entered early as a normal `schedule_entry`
  would be wiped when the week is (re)built.
- The fix is a durable, forward-looking **registry** separate from the
  schedule. The builders consult it and overlay the leave on top.

## Behaviour

- **Registry:** `planned_leave` (person, `start_date`..`end_date` inclusive,
  `PTO`|`UTO`, optional note). A leave may span multiple days.
- **Overlay:** whenever a week is built, every planned leave intersecting it
  is materialized — for each covered `(person, date)` the existing entry is
  deleted and a PTO/UTO inserted (leave wins over the shift). Triggered by:
  - Copy → next week (Home) — inside the copy's single transaction.
  - Apply default schedule (Add Schedule).
  - Manual "Apply planned leaves to this week" (Planned Leaves page).
- **Idempotent & one-entry-per-date:** re-applying is safe; a day is never
  duplicated. Deleting a leave from the registry stops future overlays but
  leaves any already-written day untouched.

## Definition of Done

- A **Planned Leaves** page: file a leave for a person over a date range,
  preview how many overlap a chosen week and apply them to it, and
  list/delete upcoming leaves (with a "show past" toggle).
- Copy-week and apply-template overlay overlapping leaves automatically and
  report how many leave-days were applied.
- Business logic in `scheduler/leaves.py` (no Streamlit); tests cover CRUD,
  validation, overlap clipping, overlay-over-shift, and idempotency.

## Out of scope

- Approval workflow, balances/accruals, notifications.
- Auto-converting leaves for people who don't yet exist (the person must be
  added first).
