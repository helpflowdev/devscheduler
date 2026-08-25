# Backlog & Milestones

Derived from the DOD. Each milestone is shippable on its own.

## M0 — Scaffold ✅
- [x] Project structure, `requirements.txt`, venv
- [x] `scheduler/db.py` schema + migration on startup
- [x] `scheduler/models.py` dataclasses + `EntryType` enum
- [x] pytest harness with temp DB fixture
- [x] `scheduler/tz.py` Pacific→Manila conversion (+ `tzdata` dep, Windows)

## M1 — People (FR-1) ✅
- [x] `scheduler/people.py`: add, list active, deactivate, duplicate-name guard
- [x] `pages/2_Manage_People.py`
- [x] Tests: duplicate active name rejected (incl. case-insensitive)

## M2 — Viewer (US-1) ✅
- [x] `scheduler/weeks.py`: Monday-anchored week math
- [x] `scheduler/entries.py`: week query (active ∪ inactive-with-entries, §11.3)
- [x] `components/week_grid.py`: Mon–Sun grid, shift/PTO/UTO badges, Manila toggle
- [x] `Home.py`: grid + week nav (prev/next/today/jump), empty state
- [x] Verified: 33 tests pass; browser-loaded, 0 console errors

## M3 — Entry flow (US-2, US-3) ✅
- [x] Page 1: person select/add + date mode (single / whole week / pick days)
- [x] Page 2: type (Shift/PTO/UTO) + time inputs + note
- [x] Bulk apply across selected dates; overwrite warning + confirm (FR-3, FR-4)
- [x] Tests: bulk apply, overwrite protection, end-vs-start, crosses-midnight
- [x] Verified in browser: add person → whole-week shift → overwrite one day
      with PTO → viewer + Manila toggle all correct (50 tests pass)

## M4 — Keep same schedule (US-4, FR-5) ✅
- [x] `scheduler/weeks.py`: `copy_week(src, dst)` in one transaction
- [x] Viewer action + overwrite confirm + cancel; auto-jump to result
- [x] Tests: exact copy, weekday mapping, empty/same-week guards,
      conflict, overwrite-clears-week, atomic rollback (56 pass)
- [x] Verified in browser on the live shared DB (copy + conflict + cancel)
- [ ] Tests: exact copy, overwrite-confirm path

## M5 — Offset / slide (US-5, FR-6) — REMOVED
- Built and shipped, then **removed at user request** (2026-05-19): the
  whole-team time-shift use case was too niche and added confusion.
  `copy_week_with_offset` / `preview_offset` / `shift_shift_times` and the
  Home offset UI + tests were deleted. Exact copy (FR-5) + per-entry edit
  cover the real need. History preserved in git if ever revived.

## M6 — Polish ✅
- [x] Overnight shift handling: ⏭ marker consistent in Pacific + Manila views
- [x] Week start + timezones centralized in `scheduler/config.py`
      (fixed Mon / Pacific+Manila per PRD §11; one place to change later)
- [x] `simplify` review (3 parallel agents) — dedup + efficiency fixes applied:
      `scheduler/util.py` (`now_iso`, `in_placeholders`), `Entry/Person.from_row`,
      shared `insert_entry` + `find_conflicts`, `_copy_core` offset refactor,
      `_lib` UI helpers (flash/conflicts/messages), case-insensitive unique
      index (migration **v2**), no-op-commit skip, `deactivate` via rowcount,
      `pacific_to_manila` lru_cache, Home avoids the correlated subquery
- [x] Live DB migrated v1→v2 cleanly (6 people / 14 entries intact, 0 loss)
- [x] README run instructions verified; 64 tests pass; all pages render,
      0 functional console errors

## M7 — Planned leaves (FR-9) ✅
- [x] Migration **v4**: `planned_leave` table (advance PTO/UTO registry),
      kept separate from `schedule_entry` so it survives week rebuilds
- [x] `scheduler/leaves.py`: add/list/delete + `overlay_leaves` (no-commit,
      joins copy's txn) + `apply_planned_leaves_to_week` (standalone)
- [x] Overlay wired into `copy_week` (single txn) and `apply_template`
      (returns `TemplateResult`); Home + Add-Schedule report leaves applied
- [x] `pages/3_Planned_Leaves.py`: file a leave (date range), preview +
      apply to a week, list/delete upcoming (toggle past)
- [x] Tests (`test_leaves.py`, 13): CRUD/validation, overlap clipping,
      overlay-wins-over-shift, one-entry-per-date, absent-from-source,
      template overlay, idempotent re-apply — full suite passes
- [x] Live DB migrated v3→v4 cleanly (additive: table + indexes)

## M8 — Split shifts + weekly hours (FR-10, FR-11) ✅
- [x] `apply_entry(mode="add")` stacks an entry on a day instead of replacing
      it; `mode="replace"` keeps the v1 overwrite-warned behaviour
- [x] `check_day_composition` (pure): shifts on one date may not overlap,
      touching blocks allowed, PTO/UTO/RD stay whole-day-exclusive; all
      target dates validated before any write (no partial bulk apply)
- [x] `shift_span` puts an overnight shift past 1440 so 22:00–06:00 and
      06:00–10:00 on one date don't falsely collide
- [x] `update_entry` / `delete_entry` act on a single entry by id, so editing
      half a split day leaves the other half alone (note preserved)
- [x] Grid cell editor is a slot picker (one slot per entry + "➕ Add a
      shift"); split days stack in the cell, compact `edit_cell_label` in
      edit mode; Add Schedule page gained a replace/add choice
- [x] Templates may list two SHIFT rows for one `(person, weekday)` — first
      replaces the cell, the rest are added alongside
- [x] No schema change; copy-forward and the leave overlay already handled
      multi-entry days (both verified by test)
- [x] **Hours** column between Person and Mon — `week_minutes_by_person` +
      `hours_label`; recomputed every render (fragment re-reads the week), so
      no compute button
- [x] Tests (`test_split_shifts.py` 39, `test_week_hours.py` 20) — full suite
      171 passes; verified live in the app (split day, overlap rejection,
      3-block day, 40h→47h total)

## PRD §11 open questions — all resolved (see PRD §11)
1. Week start: **Monday** · 2. Timezone: **Pacific base + Manila view**
3. Inactive people **visible in weeks they have entries**
4. Multi-shift/day: **shipped** in M8 (FR-10) — schema needed no change; the
   no-overlap rule is app logic
