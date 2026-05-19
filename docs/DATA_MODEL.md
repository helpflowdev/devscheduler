# Data Model — Team Schedule Viewer

SQLite. One file at `data/scheduler.db` (gitignored). Schema managed by a small migration step on startup.

## Tables

### `person`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `name` | TEXT NOT NULL | Display name. Unique among active people. |
| `is_active` | INTEGER NOT NULL DEFAULT 1 | 0 = hidden from grid, history kept. |
| `created_at` | TEXT NOT NULL | ISO-8601 UTC. |

Constraint: unique index on `name` where `is_active = 1`.

### `schedule_entry`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK AUTOINCREMENT | |
| `person_id` | INTEGER NOT NULL | FK → `person.id`. |
| `work_date` | TEXT NOT NULL | `YYYY-MM-DD`. |
| `entry_type` | TEXT NOT NULL | `SHIFT` \| `PTO` \| `UTO`. |
| `start_time` | TEXT NULL | `HH:MM` Pacific wall-clock, required iff `entry_type = SHIFT`. |
| `end_time` | TEXT NULL | `HH:MM` Pacific wall-clock, required iff `entry_type = SHIFT`. |
| `crosses_midnight` | INTEGER NOT NULL DEFAULT 0 | 1 if `end_time <= start_time`. |
| `note` | TEXT NULL | Optional. |
| `created_at` | TEXT NOT NULL | ISO-8601 UTC. |
| `updated_at` | TEXT NOT NULL | ISO-8601 UTC. |

Constraints:
- **No** DB-level `UNIQUE(person_id, work_date)` — schema must allow multiple entries per date for a future "multiple shifts/day" version (PRD §11.4). v1 enforces one-entry-per-date in app logic with overwrite warning (FR-2/FR-4); "overwrite" = delete existing rows for that `(person_id, work_date)` then insert.
- CHECK: `entry_type IN ('SHIFT','PTO','UTO')`.
- CHECK: when `entry_type = 'SHIFT'`, `start_time` and `end_time` are NOT NULL.
- Index on `(person_id, work_date)` and on `work_date` for fast week queries / overwrite lookups.

## Derived concepts

- **Week** = the 7 dates Mon..Sun. Resolved in code from any date via `date - weekday()`.
- **Copy forward (FR-5):** for each entry in week W, insert/replace into week W+1 at `work_date + 7 days`, all fields identical.
- **Offset forward (FR-6):** same as copy forward, but for `SHIFT` entries add the offset to `start_time`/`end_time`; recompute `crosses_midnight`. `PTO`/`UTO` unchanged.

## Why this shape

- Single `schedule_entry` table with a `entry_type` discriminator keeps PTO/UTO and shifts in one timeline, so the viewer is one query per week.
- `UNIQUE(person_id, work_date)` makes overwrite semantics explicit and bulk apply idempotent.
- Times as `HH:MM` text in **Pacific (`America/Los_Angeles`)** wall-clock. Pacific is the single source of truth; the Manila view is computed for display only (never stored).

## Timezone conversion (FR-8)

- Base timezone: `America/Los_Angeles`. Display alternate: `Asia/Manila`.
- Conversion is **per entry** and uses that entry's `work_date`: build a `datetime` from `work_date` + Pacific time in `ZoneInfo("America/Los_Angeles")`, then `.astimezone(ZoneInfo("Asia/Manila"))`. This makes the offset correct across Pacific DST transitions (offset is 15h or 16h depending on date).
- A Manila time may land on the **next calendar day** (Manila is ahead); the viewer must show the date shift, not just the time.
- Use stdlib `zoneinfo` (Python 3.13). No third-party tz library.
