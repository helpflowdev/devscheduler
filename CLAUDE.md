# CLAUDE.md

Team Schedule Viewer — Python 3.13 · Streamlit · SQLite. One shared instance, no auth.

## Read first

- [docs/PRD.md](docs/PRD.md) — scope and acceptance criteria
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — schema
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layout & rules
- [docs/BACKLOG.md](docs/BACKLOG.md) — build order (M0→M6); work milestones in order

## Hard rules

- **`scheduler/` never imports Streamlit.** All business logic is there and unit-tested. `app/` only renders and calls `scheduler/`.
- `apply_entry` has two modes. `mode="replace"` (default) keeps one `schedule_entry` per `(person_id, work_date)`: overwrite = delete existing rows for that pair then insert, warned + confirmed in the UI (PRD FR-4). `mode="add"` stacks a **split shift** alongside (PRD FR-10).
- **Split shifts**: a date may hold several SHIFTs as long as they don't overlap; `PTO`/`UTO`/`RD` are whole-day and exclusive. Both rules live in `check_day_composition` (pure, in `scheduler/entries.py`) — never a DB constraint. Every target date is validated *before* any write, so a bulk apply can't half-succeed. Edit/delete one entry via `update_entry`/`delete_entry` (by id) — `apply_entry(overwrite=True)` and `delete_entries` clear the whole day and would take the sibling with them.
- Copy-forward and offset-forward run in a **single transaction** — no partial rolls.
- Offset applies to `SHIFT` entries only; `PTO`/`UTO` copy unchanged.
- **Planned leaves** (advance PTO/UTO) live in their own `planned_leave` table, never `schedule_entry`. When a week is built (copy-forward, template-apply, or manual apply) overlapping leaves are **overlaid** — delete+insert PTO/UTO per `(person, date)`, leave wins over the shift. Copy-forward's overlay is inside its single transaction. Logic in `scheduler/leaves.py`; keep it idempotent and one-entry-per-date.
- Weekly hours (`week_minutes_by_person` in `scheduler/coverage.py`) sum SHIFT durations only and are recomputed on every render — the edit grid is a fragment that re-reads the week each rerun, so no "recompute" button exists or is needed.
- Times are stored as `HH:MM` Pacific (`America/Los_Angeles`) wall-clock — single source of truth. Manila (`Asia/Manila`) is a computed display view only, per-entry using `work_date` (stdlib `zoneinfo`). Never store Manila times.
- No DB `UNIQUE(person_id, work_date)` — multiple shifts/day are a real feature now, not a future one. Composition is an app-logic rule.

## Conventions

- Stdlib `sqlite3`, no ORM in v1.
- Short-lived DB connection per call; no global connection held across Streamlit reruns.
- Tests in `tests/` with a temp-file DB fixture; cover week math, copy/offset, overwrite, duplicate-name guard.
- Windows host, PowerShell. DB at `data/scheduler.db` (gitignored).

## Environment

```powershell
.venv\Scripts\Activate.ps1
streamlit run app/Home.py   # M2+
pytest
```
