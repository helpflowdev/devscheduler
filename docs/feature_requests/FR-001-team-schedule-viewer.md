# Feature Request — Team Schedule Viewer (overall)

**Submitted by:** QA Tester
**Date:** 2026-05-19
**Status:** Delivered (build b22) — formalized for tracking & regression

---

## User story

As a team lead managing a small remote team's weekly work schedule, I want a
simple web app to record and view everyone's shifts, rest days, and time off
for any week — entered in Pacific time but also readable in Manila time — and
to roll a week forward, clear it, or restore a default roster, so that I can
plan and communicate coverage in minutes instead of juggling spreadsheets.

## Context

- Small team (~5 people) on a mostly **recurring weekly pattern** with
  occasional exceptions; today there is no single source of truth.
- Each person/day is **one entry**: a Shift (start time + length), or a
  whole-day **RD** (Rest Day), **PTO** (Paid Time Off), or **UTO** (Unpaid
  Time Off). Times are 12-hour AM/PM; week starts **Monday**.
- Schedules are authored in **Pacific** (`America/Los_Angeles`) but must be
  readable in **Manila** (`Asia/Manila`) — DST-aware, with overnight shifts
  split onto the correct Manila day.
- Required operations: bulk add for a person across a single date / whole
  week / picked days; **inline edit & delete** a cell; **copy a week** to
  next week (with overwrite confirm); **clear a week**; **apply a saved
  default roster**.
- One shared instance, no per-user accounts: a shared **edit password**
  gates changes; must run on a low-cost host; data must persist in a
  managed database, with a code-stored default template as reset recovery.

## Definition of Done

- A Monday-start weekly grid shows every active person × 7 days with shift
  ranges and RD/PTO/UTO badges, in 12-hour time, with a correct Manila view
  (overnight shifts split across the right days) and people ordered by
  earliest shift start.
- Add / inline-edit / delete, copy-week (overwrite-confirmed), clear-week,
  and "apply default schedule" all work, persist, and are gated by the
  shared edit password (per session).
- A weekly **overlap** view shows who is working at the same time each day;
  the app is deployable with light/dark + brand styling, and the automated
  test suite passes.

## Scope notes (for QA accuracy)

- **De-scoped by decision:** the "slide all shifts by an offset"
  roll-forward variant was built then removed as too niche; only exact
  copy remains.
- **Out of scope (v1):** multiple shifts per person per day, per-user
  logins, approval workflows, notifications, calendar sync.

## Priority

This replaces ad-hoc spreadsheets and lets the team see and adjust coverage
in minutes; accurate visibility of who is working — including cross-timezone
overnight shifts — directly affects scheduling decisions and chat handling
time. Recommended **high** priority.
