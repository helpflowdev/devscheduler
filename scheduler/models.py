"""Domain models — plain dataclasses, no DB or Streamlit coupling."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class EntryType(str, Enum):
    """Type of a schedule entry.

    SHIFT requires start/end times. PTO/UTO/RD are whole-day, no times.
    """

    SHIFT = "SHIFT"
    PTO = "PTO"  # Paid Time Off
    UTO = "UTO"  # Unpaid Time Off
    RD = "RD"   # Rest Day (scheduled day off, not leave)

    @property
    def is_time_off(self) -> bool:
        return self in (EntryType.PTO, EntryType.UTO)

    @property
    def needs_times(self) -> bool:
        return self is EntryType.SHIFT


@dataclass(slots=True)
class Person:
    name: str
    is_active: bool = True
    created_at: str | None = None  # ISO-8601 UTC, set by the store
    id: int | None = None

    @classmethod
    def from_row(cls, row) -> "Person":
        return cls(
            id=row["id"],
            name=row["name"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )


@dataclass(slots=True)
class Entry:
    """One schedule entry. Times are Pacific (America/Los_Angeles) wall-clock.

    `start_time` / `end_time` are "HH:MM" strings and are required iff
    `entry_type == EntryType.SHIFT`. Manila time is never stored here — it is
    computed for display by `scheduler.tz`.
    """

    person_id: int
    work_date: str  # "YYYY-MM-DD"
    entry_type: EntryType
    start_time: str | None = None  # "HH:MM" Pacific, SHIFT only
    end_time: str | None = None  # "HH:MM" Pacific, SHIFT only
    crosses_midnight: bool = False
    note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    id: int | None = None

    @classmethod
    def from_row(cls, row) -> "Entry":
        keys = row.keys()
        return cls(
            id=row["id"],
            person_id=row["person_id"],
            work_date=row["work_date"],
            entry_type=EntryType(row["entry_type"]),
            start_time=row["start_time"],
            end_time=row["end_time"],
            crosses_midnight=bool(row["crosses_midnight"]),
            note=row["note"],
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None,
        )
