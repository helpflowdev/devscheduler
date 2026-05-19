# PRD — Team Schedule Viewer

**Status:** Draft v1
**Owner:** admin@helpflow.net
**Last updated:** 2026-05-17

---

## 1. Summary

A lightweight internal web tool for a team to **enter, view, and roll forward weekly work schedules**, including paid and unpaid time off. One shared instance for the whole team (no individual logins). Built in Python with Streamlit and a SQLite store.

## 2. Problem & Goals

The team currently has no single place to see who works which hours each week or who is on leave. Schedules are repetitive week to week but occasionally shift (e.g. a person's whole week slides by an hour).

**Goals**

1. See the whole team's week at a glance.
2. Enter a person's schedule for a date, a set of dates, or a whole week in a few clicks.
3. Record time off as **PTO** (Paid Time Off) or **UTO** (Unpaid Time Off).
4. Carry a week's schedule forward unchanged, or forward it with a time **offset/slide** applied.

**Non-goals (v1)**

- Authentication / per-user accounts.
- Approval workflows for leave requests.
- Payroll, billing, or hour-accrual calculations.
- Notifications, calendar sync (Google/Outlook), mobile app.
- Conflict/overlap detection beyond a simple warning.

## 3. Users & Roles

| Role | Description | Access |
|------|-------------|--------|
| Scheduler | Anyone on the team who maintains schedules | Full read/write on the shared instance |

v1 has a single trust level — everyone using the instance can edit. No login.

## 4. Definitions

| Term | Meaning |
|------|---------|
| **Shift** | A working time block on a date: start time → end time. |
| **PTO** | Paid Time Off — a full day off, paid. No times entered. |
| **UTO** | Unpaid Time Off — a full day off, unpaid. No times entered. |
| **Entry** | One row: a person + a date + a type (Shift / PTO / UTO). |
| **Week** | Mon–Sun, anchored by the Monday date (week starts **Monday**). |
| **Copy forward** | Duplicate every entry of week W into week W+1, unchanged. |
| **Offset / slide** | Copy a week forward and shift every Shift's start/end by ±H:MM. |

## 5. User Stories & Acceptance Criteria

### US-1 — View the team schedule (DOD: viewer)
*As a scheduler I want a weekly grid of all people so I can see coverage.*

- Grid: rows = people, columns = Mon–Sun of the selected week.
- Each cell shows the shift time range, or a `PTO` / `UTO` badge, or empty.
- A week picker (prev / next / jump to date) controls the visible week.
- Empty state is shown when no one has entries that week.

### US-2 — Enter who and when (DOD: name + date/week page)
*As a scheduler I want to pick a person and the date(s) or a whole week.*

- Page 1: select an existing person (or add a new name).
- Choose a date entry mode: **single date**, **multiple dates**, or **whole week**.
- Proceed to Page 2 with the selected person + dates carried over.

### US-3 — Enter the time (DOD: time page)
*As a scheduler I want to set the time for the selected date(s).*

- Page 2: choose entry type — **Shift**, **PTO**, or **UTO**.
- If Shift: enter start time and end time (validated: end > start).
- If PTO/UTO: no times required.
- Optional note field.
- Save applies the same entry to every selected date; existing entries on those dates are overwritten (with a warning listing them).

### US-4 — Keep the same schedule next week (DOD: keep same sched)
*As a scheduler I want to copy this week into next week unchanged.*

- From the viewer, "Copy week → next week" duplicates all entries.
- Warn before overwriting a target week that already has entries; require confirm.

### US-5 — Adjust next week (slide/offset) (DOD: shift/offset)
*As a scheduler I want to forward a week with all shifts slid by an offset.*

- Choose source week, target week, and an offset (e.g. `+1:00`, `-0:30`).
- Only **Shift** entries are offset; PTO/UTO copy unchanged.
- Preview the resulting week before applying.

## 6. Functional Requirements

- FR-1 People: create, list, mark inactive (inactive hidden from grid, history kept).
- FR-2 Entries: v1 enforces one entry per person per date in app logic (overwrite-warned). Schema permits multiple entries per date so a later version can add multiple shifts/day without migration.
- FR-3 Bulk apply across multiple selected dates / a full week.
- FR-4 Overwrite protection: warn + confirm before replacing existing entries.
- FR-5 Copy week forward (exact).
- FR-6 Copy week forward with Shift offset; preview required.
- FR-7 Week navigation by relative (prev/next) and absolute (date jump).
- FR-8 Times are stored as wall-clock in the **base timezone Pacific (`America/Los_Angeles`, "PST/PDT")**. The viewer offers a **Manila (`Asia/Manila`) conversion view** toggle that converts each entry using its own `work_date` (so Pacific DST is handled correctly per date).

## 7. Data Model (summary)

See [DATA_MODEL.md](DATA_MODEL.md). Core tables: `person`, `schedule_entry`.

## 8. UX Flow

```
[Viewer]  ──"Add / Edit"──▶  [Page 1: Person + Dates]  ──▶  [Page 2: Type + Time]  ──save──▶  [Viewer]
   │
   ├─"Copy week → next"──────▶ confirm ─────────────────────────────────────────────▶ [Viewer]
   └─"Forward with offset"──▶ [pick offset + preview] ─── apply ─────────────────────▶ [Viewer]
```

## 9. Edge Cases

- Overnight shift (end < start) → treated as crossing midnight; flag in v1, allow with warning.
- Offset pushes a shift past midnight → allowed, flagged in preview.
- Copying onto a partially filled week → per-date overwrite warning.
- Adding a person whose name already exists → reject duplicate active names.
- Selecting "whole week" then also individual dates → week mode wins.

## 10. Success Metrics

- A full week for one person can be entered in < 30 seconds.
- Rolling a week forward (exact or offset) takes < 3 clicks.
- Zero data loss on overwrite (always warned + confirmed).

## 11. Resolved Decisions

1. **Week start = Monday.**
2. **Timezone:** base storage in Pacific (`America/Los_Angeles`); viewer has a Manila (`Asia/Manila`) conversion view toggle. Conversion is per-entry using `work_date` so Pacific DST is correct.
3. **Inactive people remain visible in historical/past weeks** (only hidden from current-week editing scope as needed; history preserved).
4. **Multiple shifts per person per day:** out of scope for v1 (one entry/date enforced in app logic) but the schema must not block it — no DB-level uniqueness on `(person_id, work_date)`.
