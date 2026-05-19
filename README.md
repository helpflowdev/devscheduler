# Team Schedule Viewer

A lightweight internal tool to enter, view, and roll forward weekly team schedules,
including PTO (Paid Time Off) and UTO (Unpaid Time Off).

- **Stack:** Python 3.13 · Streamlit · SQLite
- **Model:** one shared instance; no per-user login, optional shared-password
  gate for public hosting (see [docs/PRD.md](docs/PRD.md))

## Docs

| File | What |
|------|------|
| [docs/PRD.md](docs/PRD.md) | Product requirements, user stories, scope |
| [docs/DATA_MODEL.md](docs/DATA_MODEL.md) | SQLite schema and derived logic |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Code layout and design principles |
| [docs/BACKLOG.md](docs/BACKLOG.md) | Milestones M0–M6 |

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run locally

```powershell
streamlit run app/Home.py
```

DB defaults to `./data/scheduler.db`. Override with the `SCHEDULER_DB_PATH`
env var. No password locally unless `SCHEDULER_PASSWORD` is set.

## Test

```powershell
pytest
```

## Deploy (Render)

Single web service + a persistent disk keeps the shared SQLite file across
restarts/redeploys. Config lives in [render.yaml](render.yaml).

1. Push this repo to GitHub/GitLab.
2. Render → **New → Blueprint** → pick the repo. It reads `render.yaml`:
   a `starter` web service, a 1 GB disk mounted at `/var/scheduler-data`,
   and `SCHEDULER_DB_PATH` pointed at it.
3. Set **`SCHEDULER_PASSWORD`** in the Render dashboard (Environment tab).
   Without it the app is open to anyone with the URL — see below.
4. Deploy. Health check is `/_stcore/health`.

**Why not Vercel:** Streamlit is a long-running websocket server and the
app needs a persistent writable disk for SQLite — neither fits Vercel's
serverless model. Render (or Fly.io/Railway) with a disk is the right fit.

### Authentication

The app itself has no per-user login (PRD design). On a public host this
means a single **shared password** gate, enabled by setting
`SCHEDULER_PASSWORD`. Treat it as a deterrent, not strong security; for
anything sensitive put it behind a VPN/SSO proxy instead.

### Backups

Render disks are durable but **not** auto-backed-up. Snapshot the DB from
the Render Shell (or a scheduled job):

```bash
python scripts/backup_db.py
```

Writes a timestamped `scheduler-*.db` next to the live DB via SQLite's
online backup API (safe while running). Download/copy snapshots off the
instance for real disaster recovery.

### Scaling note

One instance only (the disk binds to a single service); deploys cause
brief downtime. Fine for one team. If you outgrow it, migrate the storage
layer (`scheduler/db.py` + raw SQL) to managed Postgres — it's isolated by
design.
