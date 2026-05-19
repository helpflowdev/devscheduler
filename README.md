# Team Schedule Viewer

A lightweight internal tool to enter, view, and roll forward weekly team schedules,
including PTO (Paid Time Off) and UTO (Unpaid Time Off).

- **Stack:** Python 3.13 · Streamlit · SQLite (local/tests) / Postgres (prod)
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

DB backend is chosen by env: **`DATABASE_URL`** (Postgres) if set, else a
local SQLite file (`./data/scheduler.db`, or `SCHEDULER_DB_PATH`). No
password locally unless `SCHEDULER_PASSWORD` is set. The same code runs on
both — tests run on SQLite.

## Test

```powershell
pytest
```

## Deploy — Streamlit Community Cloud + free Postgres ($0)

Free, persistent, no servers to manage. ~10 minutes.

**1. Create a free Postgres database.** Either works:
- **Supabase** → New project → Settings → Database → copy the
  **connection string** (URI). Use the *direct* connection.
- **Neon** → New project → copy the `postgresql://...` connection string.

**2. Deploy the app.** Go to **share.streamlit.io** → sign in with GitHub →
**Create app** → pick `helpflowdev/devscheduler`, branch `main`, main file
`app/Home.py`.

**3. Add secrets.** In the app's **⋮ → Settings → Secrets**, paste:

```toml
DATABASE_URL = "postgresql://user:pass@host:5432/dbname"
SCHEDULER_PASSWORD = "pick-a-shared-password"
```

(`postgres://`/`postgresql://` are auto-normalized to the right driver.)

**4. Save & deploy.** First load runs the schema migration automatically.
You get a public URL like `https://<app>.streamlit.app` — that's where the
team uses it. There's no extra cost; the free tiers cover a small team.

If `DATABASE_URL` is missing the app falls back to an **ephemeral** SQLite
file that resets on every redeploy — so the Postgres secret is what makes
data persist. `SCHEDULER_PASSWORD` is required here, or the public URL is
open to anyone (see Authentication).

### Verify the database (recommended before first real use)

Point the env var at your Postgres URL and run the self-check — it
connects, migrates, and does a rolled-back round trip (writes nothing):

```powershell
$env:DATABASE_URL = "postgresql://user:pass@host:5432/dbname"
.venv\Scripts\python.exe scripts/check_db.py   # prints "Database is ready."
```

> Note: the Postgres path is code-complete and the query logic is covered
> by the test suite (run on SQLite), but it has **not** been exercised
> against a live Postgres in this environment. `check_db.py` is that
> confirmation — run it once after setting `DATABASE_URL`.

### Authentication

No per-user login (PRD design). Two optional shared passwords:

- **`SCHEDULER_PASSWORD`** — asked once to open the app (view access).
- **`SCHEDULER_EDIT_PASSWORD`** — asked again before any edit: the
  Add Schedule / Manage People pages and Home's Edit mode. Per session
  (re-asked on refresh / new tab / new browser). Set
  **`SCHEDULER_EDIT_TTL_MIN`** (e.g. `10`) to also expire the unlock
  after N idle minutes; leave unset for session-long (recommended).

Both are deterrents, not strong security; for sensitive data put the app
behind SSO/VPN as well.

### Theme

Brand blue accent is always on. Each viewer picks **Light / Dark / Use
system** via the **☰ menu → Settings → Theme** (Streamlit's built-in
switch — there's no in-page toggle for the whole app). The weekly-overlap
chart has its own Dark/Light control since it's a custom chart.

### Backups

Use your Postgres provider's built-in backups (Supabase/Neon both keep
automatic backups / point-in-time on free tiers) or run `pg_dump` against
`DATABASE_URL` on a schedule. `scripts/backup_db.py` is for the **local
SQLite** file only.

### Alternative: Render with SQLite on a disk (paid)

[render.yaml](render.yaml) is kept for a single paid Render service +
persistent disk (no external DB, but ~$7/mo and single-instance). The
Streamlit Cloud + Postgres path above is preferred for a free team deploy.

**Why not Vercel:** Streamlit is a long-running websocket server — it
doesn't fit Vercel's serverless model regardless of database.
