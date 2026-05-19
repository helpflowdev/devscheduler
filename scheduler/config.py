"""Central configuration.

Per PRD §11 these are fixed for v1 (week starts Monday; storage is Pacific
with a Manila display view). They live here so a future version can make
them configurable without touching call sites.
"""

from __future__ import annotations

# Week starts Monday (PRD §11.1). Index 0 == Monday, matching
# datetime.date.weekday().
WEEK_START_WEEKDAY = 0
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Storage is wall-clock in this zone; it is the single source of truth.
BASE_TZ_NAME = "America/Los_Angeles"  # Pacific (PST/PDT)
# Alternate view computed for display only — never stored (PRD §11.2).
DISPLAY_TZ_NAME = "Asia/Manila"
