"""Manage People — add, list, deactivate.

Names are unique among active people; deactivating frees the name and keeps
history (PRD §11.3 / FR-1).
"""

from __future__ import annotations

import streamlit as st

from _lib import (
    get_db,
    require_edit_unlock,
    require_password,
    set_flash,
    show_flash,
    theme_control,
)
from scheduler.errors import DomainError
from scheduler.people import add_person, deactivate_person, list_people

st.set_page_config(page_title="Manage People", page_icon="👥")
theme_control()
require_password()
st.title("👥 Manage People")
require_edit_unlock("manage people")
show_flash()

with st.form("add_person", clear_on_submit=True):
    name = st.text_input("Name")
    submitted = st.form_submit_button("Add person")

show_inactive = st.toggle("Show deactivated people")

# One connection per render handles the add/deactivate mutation and the
# list read together (connect-per-interaction — ARCHITECTURE.md).
with get_db() as conn:
    if submitted:
        try:
            person = add_person(conn, name)
            set_flash(f"Added {person.name}.")
            st.rerun()
        except DomainError as exc:
            st.error(str(exc))

    people = list_people(conn, include_inactive=show_inactive)

if not people:
    st.info("No people yet. Add someone above.")
else:
    for p in people:
        col_name, col_status, col_action = st.columns([3, 1, 1])
        col_name.write(p.name)
        col_status.write("✅ active" if p.is_active else "💤 inactive")
        if p.is_active and col_action.button("Deactivate",
                                             key=f"deact_{p.id}"):
            with get_db() as conn:
                deactivate_person(conn, p.id)
            st.rerun()
