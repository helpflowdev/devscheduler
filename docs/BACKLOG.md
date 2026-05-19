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

## M5 — Offset / slide (US-5, FR-6) ✅
- [x] `scheduler/weeks.py`: `copy_week_with_offset` (shared `_copy_core`)
- [x] Offset applies to SHIFT only; PTO/UTO unchanged; crosses_midnight recomputed
- [x] `preview_offset` (read-only) + preview-before-apply UI + overwrite confirm
- [x] Tests: ±offset, midnight-wrap recompute, zero-offset guard, PTO untouched,
      preview writes nothing (64 pass)
- [x] Verified in browser: preview renders correctly (apply left to unit tests
      — live shared DB)

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

## PRD §11 open questions — all resolved (see PRD §11)
1. Week start: **Monday** · 2. Timezone: **Pacific base + Manila view**
3. Inactive people **visible in weeks they have entries** · 4. Multi-shift/day:
   schema-ready, app enforces one/day in v1
4. Multiple shifts per day (future version?)
