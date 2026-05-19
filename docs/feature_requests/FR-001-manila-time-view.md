# Feature Request — Manila-time schedule view

**Submitted by:** QA Tester
**Date:** 2026-05-19
**Status:** Delivered (build b22) — formalized for tracking/regression

---

## User story

As a team member coordinating a Pacific-based roster from Manila, I want to
toggle the weekly schedule into Manila time and have each shift appear on the
correct **Manila** day — split across midnight when it crosses — so that I can
read everyone's hours in my own timezone without doing mental math or
misreading overnight shifts.

## Context

- Schedules are stored and entered in **Pacific** (`America/Los_Angeles`);
  most viewers work in **Manila** (`Asia/Manila`), a 15–16 hour difference.
- A Pacific daytime shift maps to a Manila **overnight that spans two
  calendar days** (e.g. 7:00 AM–3:00 PM PST → 10:00 PM Mon to 6:00 AM Tue).
- Before this change the converted time was shown only in the original
  Pacific day's cell (e.g. "10:00 PM–6:00 AM" on Monday), implying an
  impossible same-day 24-hour shift and causing misreads.
- The Pacific↔Manila gap changes with US daylight saving (15h during PDT,
  16h during PST), so conversion must be **per shift date**, not a fixed
  offset.
- Whole-day entries (RD / PTO / UTO) have no clock time and must stay on
  their assigned date regardless of the timezone view.

## Definition of Done

- Toggling **Manila time** re-buckets each shift onto its Manila day and
  splits at midnight — e.g. Mon 7:00 AM–3:00 PM PST shows as **Mon
  10:00 PM–12:00 AM** and **Tue 12:00 AM–6:00 AM**.
- Conversion is DST-correct: the same shift uses the offset valid for its
  own date (15h PDT vs 16h PST), verified across a DST boundary.
- Whole-day RD/PTO/UTO remain on their original date; editing stays on the
  stored Pacific date (Manila is a read-only view transformation).

## Priority

Manila-based staff use this daily to read coverage; without correct day
placement they misjudge who is working overnight, which risks coverage gaps
and scheduling errors. This directly improves how fast and accurately the
team can read the roster — recommended **medium-high** priority.
