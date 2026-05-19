"""Hot backup of the SQLite database.

Render disks are durable but not auto-backed-up. Run this from the Render
Shell (or locally) to snapshot the DB safely while the app is running, via
SQLite's online backup API:

    python scripts/backup_db.py [dest_dir]

Writes ``scheduler-YYYYMMDD-HHMMSS.db`` into ``dest_dir`` (default: the
DB's own directory). For real disaster recovery, copy the snapshot off the
instance (download via Render Shell, or push to object storage).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler.db import DEFAULT_DB_PATH  # noqa: E402


def main() -> None:
    src = Path(DEFAULT_DB_PATH)
    if not src.exists():
        raise SystemExit(f"No database at {src}")

    dest_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else src.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"scheduler-{stamp}.db"

    with sqlite3.connect(src) as s, sqlite3.connect(dest) as d:
        s.backup(d)  # consistent snapshot even under concurrent writes
    print(f"Backed up {src} → {dest}")


if __name__ == "__main__":
    main()
