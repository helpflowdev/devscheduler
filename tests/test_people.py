"""Person CRUD + duplicate-name guard (M1)."""

from __future__ import annotations

import pytest

from scheduler.errors import DuplicateNameError, NotFoundError, ValidationError
from scheduler.people import (
    add_person,
    deactivate_person,
    get_person,
    list_people,
)


def test_add_and_get(db):
    p = add_person(db, "Alice")
    assert p.id is not None and p.is_active is True
    assert get_person(db, p.id).name == "Alice"


def test_name_is_trimmed(db):
    assert add_person(db, "  Bob  ").name == "Bob"


def test_blank_name_rejected(db):
    with pytest.raises(ValidationError):
        add_person(db, "   ")


def test_duplicate_active_name_rejected(db):
    add_person(db, "Cara")
    with pytest.raises(DuplicateNameError):
        add_person(db, "Cara")


def test_duplicate_check_is_case_insensitive(db):
    add_person(db, "Dana")
    with pytest.raises(DuplicateNameError):
        add_person(db, "dana")


def test_name_freed_after_deactivation(db):
    p = add_person(db, "Eve")
    deactivate_person(db, p.id)
    reused = add_person(db, "Eve")  # allowed again
    assert reused.id != p.id


def test_list_excludes_inactive_by_default(db):
    a = add_person(db, "Ann")
    b = add_person(db, "Zed")
    deactivate_person(db, b.id)
    assert [p.name for p in list_people(db)] == ["Ann"]
    names = {p.name for p in list_people(db, include_inactive=True)}
    assert names == {"Ann", "Zed"}
    assert a.name in names


def test_list_is_name_sorted(db):
    for n in ("Charlie", "alice", "Bob"):
        add_person(db, n)
    assert [p.name for p in list_people(db)] == ["alice", "Bob", "Charlie"]


def test_deactivate_missing_raises(db):
    with pytest.raises(NotFoundError):
        deactivate_person(db, 999)
