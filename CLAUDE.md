# CLAUDE.md

Team Schedule Viewer — Python 3.13 · Streamlit · SQLite. One shared instance, no auth.

## Read first

- [docs/PRD.md](docs/PRD.md) — scope and acceptance criteria
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — schema
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layout & rules
- [docs/BACKLOG.md](docs/BACKLOG.md) — build order (M0→M6); work milestones in order

## Hard rules

- **`scheduler/` never imports Streamlit.** All business logic is there and unit-tested. `app/` only renders and calls `scheduler/`.
- v1: one `schedule_entry` per `(person_id, work_date)` enforced in app logic. Overwrite = delete existing rows for that pair then insert, warned + confirmed in the UI (PRD FR-4).
- Copy-forward and offset-forward run in a **single transaction** — no partial rolls.
- Offset applies to `SHIFT` entries only; `PTO`/`UTO` copy unchanged.
- Times are stored as `HH:MM` Pacific (`America/Los_Angeles`) wall-clock — single source of truth. Manila (`Asia/Manila`) is a computed display view only, per-entry using `work_date` (stdlib `zoneinfo`). Never store Manila times.
- No DB `UNIQUE(person_id, work_date)`. v1 enforces one entry/date in app logic (overwrite = delete+insert, warned). Schema stays open for multiple shifts/day later.

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
