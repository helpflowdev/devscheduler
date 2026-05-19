"""Person CRUD (FR-1).

Names are unique among *active* people only — deactivating frees the name
for reuse. Inactive people are kept so historical weeks still resolve
(PRD §11.3).
"""

from __future__ import annotations

import sqlite3

from scheduler.errors import DuplicateNameError, NotFoundError, ValidationError
from scheduler.models import Person
from scheduler.util import now_iso


def add_person(conn: sqlite3.Connection, name: str) -> Person:
    """Create an active person.

    Raises ValidationError on blank name; DuplicateNameError if an active
    person already has that name. Uniqueness (case-insensitive) is enforced
    by the partial unique index, so a plain insert is both correct and
    race-free — no pre-check needed.
    """
    clean = name.strip()
    if not clean:
        raise ValidationError("Name cannot be empty.")

    try:
        cur = conn.execute(
            "INSERT INTO person(name, is_active, created_at) VALUES (?, 1, ?)",
            (clean, now_iso()),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise DuplicateNameError(
            f"An active person named '{clean}' already exists."
        ) from exc

    return get_person(conn, cur.lastrowid)


def get_person(conn: sqlite3.Connection, person_id: int) -> Person:
    row = conn.execute(
        "SELECT id, name, is_active, created_at FROM person WHERE id = ?",
        (person_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"No person with id {person_id}.")
    return Person.from_row(row)


def list_people(
    conn: sqlite3.Connection, *, include_inactive: bool = False
) -> list[Person]:
    """Active people, name-sorted. With ``include_inactive`` returns all."""
    sql = "SELECT id, name, is_active, created_at FROM person"
    if not include_inactive:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY name COLLATE NOCASE"
    return [Person.from_row(r) for r in conn.execute(sql).fetchall()]


def deactivate_person(conn: sqlite3.Connection, person_id: int) -> None:
    """Hide a person from active lists; history is preserved (PRD §11.3)."""
    cur = conn.execute(
        "UPDATE person SET is_active = 0 WHERE id = ?", (person_id,)
    )
    if cur.rowcount == 0:
        conn.rollback()
        raise NotFoundError(f"No person with id {person_id}.")
    conn.commit()
