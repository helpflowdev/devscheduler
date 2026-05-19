"""Thin helpers shared by Streamlit pages.

The `app/` layer only renders and calls `scheduler/`. Connections are
short-lived per interaction (Streamlit reruns each action) — never hold a
global connection (ARCHITECTURE.md).
"""

from __future__ import annotations

import hmac
import os
import sys
from contextlib import contextmanager
from pathlib import Path

# Make the project root importable when Streamlit runs app/Home.py.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402

from scheduler.db import connect  # noqa: E402
from scheduler.models import Entry, EntryType  # noqa: E402

_FLASH_KEY = "_flash"


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def require_password() -> None:
    """Gate the page behind a shared password when one is configured.

    No-op if ``SCHEDULER_PASSWORD`` is unset (local/dev). On a public host
    (Render) set it so the otherwise-unauthenticated tool isn't open to
    anyone with the link. Call once at the top of every page.
    """
    expected = os.environ.get("SCHEDULER_PASSWORD")
    if not expected or st.session_state.get("_authed"):
        return
    st.title("🔒 Team Schedule Viewer")
    entered = st.text_input("Password", type="password")
    if entered:
        if hmac.compare_digest(entered, expected):
            st.session_state["_authed"] = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()


def set_flash(message: str) -> None:
    """Stash a success message to show after the next ``st.rerun()``."""
    st.session_state[_FLASH_KEY] = message


def show_flash() -> None:
    """Render and clear a pending flash. Call once at the top of a page."""
    if st.session_state.get(_FLASH_KEY):
        st.success(st.session_state.pop(_FLASH_KEY))


def entries_phrase(n: int) -> str:
    """``"1 entry"`` / ``"3 entries"``."""
    return f"{n} entr{'y' if n == 1 else 'ies'}"


def entry_detail(e: Entry) -> str:
    """How an existing entry reads in a conflict list."""
    if e.entry_type is EntryType.SHIFT:
        return f"{e.start_time}–{e.end_time}"
    return e.entry_type.value


def saved_message(verb: str, created: int, overwritten: int) -> str:
    """Uniform 'Saved N entries (replaced M).' style message."""
    tail = f" (replaced {overwritten})." if overwritten else "."
    return f"{verb} {entries_phrase(created)}{tail}"


def render_conflicts(pending: dict[str, list[Entry]]) -> None:
    """List the conflicting entries grouped by date."""
    for d in sorted(pending):
        for e in pending[d]:
            st.write(f"- **{d}**: {entry_detail(e)}")
