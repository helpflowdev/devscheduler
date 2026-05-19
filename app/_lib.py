"""Thin helpers shared by Streamlit pages.

The `app/` layer only renders and calls `scheduler/`. Connections are
short-lived per interaction (Streamlit reruns each action) — never hold a
global connection (ARCHITECTURE.md).
"""

from __future__ import annotations

import hmac
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# Make the project root importable when Streamlit runs app/Home.py.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402


def _bridge_secrets() -> None:
    """Expose Streamlit secrets as env vars before the DB layer reads them.

    `scheduler.db` reads `DATABASE_URL` from `os.environ`. On Streamlit
    Community Cloud you set these in the app's Secrets; this also makes a
    local `.streamlit/secrets.toml` work. Real env vars win.
    """
    for key in ("DATABASE_URL", "SCHEDULER_PASSWORD",
                "SCHEDULER_EDIT_PASSWORD", "SCHEDULER_EDIT_TTL_MIN"):
        if os.environ.get(key):
            continue
        try:
            if key in st.secrets:
                os.environ[key] = str(st.secrets[key])
        except Exception:
            pass  # no secrets file locally — fine


_bridge_secrets()

from scheduler.db import connect  # noqa: E402
from scheduler.models import Entry, EntryType  # noqa: E402
from scheduler.timefmt import range_12h  # noqa: E402

# Bump on each deploy so a stale Streamlit Cloud build is obvious.
BUILD = "2026-05-19 · b18 · default schedule updated"

_FLASH_KEY = "_flash"

# HelpFlow brand palette (brand guideline p.4).
BRAND = {
    "blue": "#2EA3F2",
    "gray": "#A6A6A6",
    "peach": "#FFE4B0",
    "lavender": "#E1E0FF",
    "sky": "#C3EDFF",
    "navy": "#111229",
}
# Entry-type → (background, text) chips.
TYPE_STYLE = {
    "PTO": (BRAND["peach"], BRAND["navy"]),
    "UTO": (BRAND["lavender"], BRAND["navy"]),
    "RD": (BRAND["sky"], BRAND["navy"]),
}


def badge(text: str, bg: str, fg: str) -> str:
    """A small colored chip (HTML) for use with unsafe_allow_html."""
    return (
        f"<span style='background:{bg};color:{fg};padding:2px 8px;"
        f"border-radius:10px;font-size:0.85em;white-space:nowrap'>"
        f"{text}</span>"
    )


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


# Hide Streamlit's per-element toolbar (the oversized fullscreen +
# raw "Show data"); we provide a sized popup instead.
_COMMON_CSS = "[data-testid='stElementToolbar']{display:none}"

_THEME_CSS = {
    "Dark": (
        ".stApp{background-color:#111229;color:#FFFFFF}"
        "[data-testid='stSidebar']{background-color:#1E2147}"
        ".stApp h1,.stApp h2,.stApp h3,.stApp p,.stApp label,"
        ".stApp .stMarkdown{color:#FFFFFF}"
        # Every button navy w/ white label (covers secondary, form-submit,
        # popover, etc.) so none are white-on-white…
        ".stApp button{background-color:#1E2147!important;"
        "color:#FFFFFF!important;border:1px solid #3A3F6B!important}"
        ".stApp button *{color:#FFFFFF!important}"
        # …but keep primary (Save/Apply) on brand blue.
        ".stApp [data-testid='stBaseButton-primary']{"
        "background-color:#2EA3F2!important;border-color:#2EA3F2!important}"
        + _COMMON_CSS
    ),
    "Light": (
        ".stApp{background-color:#FFFFFF;color:#111229}"
        "[data-testid='stSidebar']{background-color:#F2F3FF}"
        ".stApp h1,.stApp h2,.stApp h3,.stApp p,.stApp label,"
        ".stApp .stMarkdown{color:#111229}"
        + _COMMON_CSS
    ),
}


def theme_control() -> str:
    """Minimal dark-mode switch pinned to the bottom of the sidebar.

    Returns "Dark"/"Light"; also drives the overlap chart. Styling
    overlay only (Streamlit has no Python API for its native theme), so a
    few native pop-ups keep default colors.
    """
    # Spacer pushes the switch into the lower part of the sidebar
    # (robust across Streamlit versions — no internal-DOM selectors).
    st.sidebar.markdown("<div style='height:72vh'></div>",
                        unsafe_allow_html=True)
    dark = st.sidebar.toggle("🌙 Dark mode", value=True, key="_app_dark")
    choice = "Dark" if dark else "Light"
    st.markdown(f"<style>{_THEME_CSS[choice]}</style>",
                unsafe_allow_html=True)
    return choice


def edit_unlocked() -> bool:
    """Is the current session allowed to edit?

    True when no ``SCHEDULER_EDIT_PASSWORD`` is configured (no extra gate),
    or it was entered this session. If ``SCHEDULER_EDIT_TTL_MIN`` is set,
    the unlock expires that many minutes after it was entered.
    """
    pw = os.environ.get("SCHEDULER_EDIT_PASSWORD")
    if not pw:
        return True
    at = st.session_state.get("_edit_ok_at")
    if not at:
        return False
    ttl = os.environ.get("SCHEDULER_EDIT_TTL_MIN")
    if ttl:
        try:
            if time.time() - at > float(ttl) * 60:
                st.session_state.pop("_edit_ok_at", None)
                return False
        except ValueError:
            pass
    return True


def require_edit_unlock(action: str = "make changes") -> None:
    """Prompt for the edit password before an editing surface.

    Per session by default (re-asked on refresh / new tab). Set
    ``SCHEDULER_EDIT_TTL_MIN`` to also expire the unlock after N idle
    minutes. No-op if ``SCHEDULER_EDIT_PASSWORD`` is unset. Halts the
    script (``st.stop``) until unlocked.
    """
    pw = os.environ.get("SCHEDULER_EDIT_PASSWORD")
    if not pw or edit_unlocked():
        return
    st.warning(f"🔒 Enter the edit password to {action}.")
    entered = st.text_input("Edit password", type="password",
                            key="_edit_pw")
    if entered:
        if hmac.compare_digest(entered, pw):
            st.session_state["_edit_ok_at"] = time.time()
            st.rerun()
        st.error("Wrong edit password.")
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
    """How an existing entry reads in a conflict list (12-hour)."""
    if e.entry_type is EntryType.SHIFT:
        return range_12h(e.start_time, e.end_time)
    return e.entry_type.value


def pick_time_12h(label: str, key: str, default_hhmm: str) -> str:
    """12-hour AM/PM time picker (Streamlit's time_input is 24h-only).

    Returns canonical 24-hour ``"HH:MM"``. Minutes in 5-min steps.
    """
    dh, dm = (int(x) for x in default_hhmm.split(":"))
    minutes = [f"{i:02d}" for i in range(0, 60, 5)]
    c1, c2, c3 = st.columns(3)
    hour = c1.selectbox(
        label, list(range(1, 13)),
        index=(dh % 12 or 12) - 1, key=f"{key}_h",
    )
    minute = c2.selectbox(
        "Min", minutes,
        index=(dm // 5) if dm % 5 == 0 else 0, key=f"{key}_m",
    )
    ampm = c3.selectbox(
        "AM/PM", ["AM", "PM"],
        index=0 if dh < 12 else 1, key=f"{key}_ap",
    )
    h24 = hour % 12 + (12 if ampm == "PM" else 0)
    return f"{h24:02d}:{minute}"


def pick_duration(key: str, default_min: int = 480) -> int:
    """Shift length as hours + minutes (5-min steps). Returns minutes.

    Default 8h. Used instead of an end-time picker — pick when it starts
    and how long it runs; the end is derived (handles overnight cleanly).
    """
    dh, dm = divmod(default_min, 60)
    minutes = [f"{i:02d}" for i in range(0, 60, 5)]
    c1, c2 = st.columns(2)
    hours = c1.number_input(
        "Hours", min_value=0, max_value=23, value=dh, key=f"{key}_dh"
    )
    mins = c2.selectbox(
        "Minutes", minutes,
        index=(dm // 5) if dm % 5 == 0 else 0, key=f"{key}_dm",
    )
    return int(hours) * 60 + int(mins)


def pick_time_12h_stacked(key: str, default_hhmm: str) -> str:
    """Like :func:`pick_time_12h` but no st.columns — safe inside a
    popover that already lives in a grid column."""
    dh, dm = (int(x) for x in default_hhmm.split(":"))
    minutes = [f"{i:02d}" for i in range(0, 60, 5)]
    hour = st.selectbox("Start hour", list(range(1, 13)),
                        index=(dh % 12 or 12) - 1, key=f"{key}_h")
    minute = st.selectbox("Start min", minutes,
                          index=(dm // 5) if dm % 5 == 0 else 0,
                          key=f"{key}_m")
    ampm = st.selectbox("AM/PM", ["AM", "PM"],
                        index=0 if dh < 12 else 1, key=f"{key}_ap")
    return f"{hour % 12 + (12 if ampm == 'PM' else 0):02d}:{minute}"


def pick_duration_stacked(key: str, default_min: int = 480) -> int:
    """Like :func:`pick_duration` but no st.columns (popover-safe)."""
    dh, dm = divmod(default_min, 60)
    minutes = [f"{i:02d}" for i in range(0, 60, 5)]
    hours = st.number_input("Length — hours", min_value=0, max_value=23,
                            value=dh, key=f"{key}_dh")
    mins = st.selectbox("Length — minutes", minutes,
                        index=(dm // 5) if dm % 5 == 0 else 0,
                        key=f"{key}_dm")
    return int(hours) * 60 + int(mins)


def saved_message(verb: str, created: int, overwritten: int) -> str:
    """Uniform 'Saved N entries (replaced M).' style message."""
    tail = f" (replaced {overwritten})." if overwritten else "."
    return f"{verb} {entries_phrase(created)}{tail}"


def render_conflicts(pending: dict[str, list[Entry]]) -> None:
    """List the conflicting entries grouped by date."""
    for d in sorted(pending):
        for e in pending[d]:
            st.write(f"- **{d}**: {entry_detail(e)}")
