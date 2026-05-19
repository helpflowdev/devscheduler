# Architecture — Team Schedule Viewer

## Stack

- **UI:** Streamlit (multipage app)
- **Storage:** SQLite via `sqlite3` (stdlib) — no ORM in v1
- **Language:** Python 3.13
- **Run:** `streamlit run app/Home.py`

## Layout

```
Scheduler/
├─ app/
│  ├─ Home.py                 # Viewer: weekly team grid + week nav + roll-forward actions
│  ├─ pages/
│  │  ├─ 1_Add_Schedule.py    # person + date(s)/week → type + time
│  │  ├─ 2_Manage_People.py   # Add / deactivate people
│  │  └─ 3_Edit_or_Delete.py  # change or remove one person/date entry
│  └─ components/
│     ├─ week_grid.py         # Render the Mon–Sun grid
│     └─ coverage_chart.py    # Weekly overlap (per-day boxes)
├─ scheduler/                 # Pure logic, no Streamlit imports (unit-testable)
│  ├─ db.py                   # Connection, migrations, schema
│  ├─ people.py               # Person CRUD
│  ├─ entries.py              # Entry create/bulk-apply/overwrite
│  ├─ weeks.py                # Week math, copy-forward, offset-forward
│  └─ models.py               # Dataclasses: Person, Entry, EntryType enum
├─ tests/                     # pytest, against scheduler/ logic
├─ data/                      # scheduler.db (gitignored)
├─ docs/                      # PRD, data model, this file, backlog
├─ requirements.txt
└─ README.md
```

## Key principle

**All business logic lives in `scheduler/` and never imports Streamlit.** The `app/` layer only calls `scheduler/` functions and renders. This keeps copy-forward / offset / overwrite logic testable with pytest and the UI thin.

## Data flow

1. Streamlit page collects input → calls a `scheduler/` function.
2. `scheduler/` validates, runs the SQLite transaction, returns dataclasses or raises a domain error.
3. Page renders result or the error message.

## State & concurrency

- One shared SQLite file. Streamlit reruns per interaction; open a short-lived connection per call (or `st.connection`), don't hold global connections.
- Multi-writer is rare for this team size; rely on SQLite's file lock + last-write-wins, surfaced via the overwrite-warning UX (FR-4).
- Wrap copy-forward / offset-forward in a single transaction so a partial roll never persists.

## Migrations

`scheduler/db.py` runs idempotent `CREATE TABLE IF NOT EXISTS` + a `schema_version` pragma check on first connection. No external migration tool in v1.

## Testing

- `pytest` on `scheduler/` with an in-memory or temp-file DB.
- Priority coverage: week math, copy-forward, offset across midnight, overwrite protection, duplicate-name rejection.
