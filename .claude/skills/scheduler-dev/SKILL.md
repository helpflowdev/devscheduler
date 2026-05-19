---
name: scheduler-dev
description: Dev workflow for the Team Schedule Viewer — set up the venv, run the Streamlit app, run tests, or reset the local SQLite database. Use when the user says "run the app", "start the scheduler", "run tests", "reset the db", or sets up the environment.
---

# Scheduler Dev Workflow

Windows host, PowerShell. Project root is the Scheduler directory.

## Set up environment (first time)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run the app

```powershell
.venv\Scripts\Activate.ps1
streamlit run app/Home.py
```

Runs at http://localhost:8501. (`app/Home.py` exists only from milestone M2 — check docs/BACKLOG.md.)

## Run tests

```powershell
.venv\Scripts\Activate.ps1
pytest -q
```

## Reset the local database

The DB is `data/scheduler.db` (gitignored). Deleting it forces a clean schema rebuild on next startup. **Confirm with the user first — this destroys all schedule data.**

```powershell
Remove-Item -Force data\scheduler.db
```

## Notes

- Never put business logic in `app/` — it belongs in `scheduler/` (see CLAUDE.md).
- After schema changes in `scheduler/db.py`, reset the DB so migrations apply cleanly.
