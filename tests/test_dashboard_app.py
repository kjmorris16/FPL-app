import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.db as db_module
from src.db import SCHEMA

# AppTest.from_file() resolves a *relative* path against the directory of
# the file that calls it (this test file's own directory, tests/), not the
# project root -- passing an absolute path sidesteps that entirely.
APP_PATH = str(Path(__file__).resolve().parent.parent / "src" / "dashboard" / "app.py")


@pytest.fixture
def empty_db(tmp_path, monkeypatch):
    """Points src.db at a fresh, empty (schema-only) SQLite file for the
    duration of the test, so the dashboard's real data/fpl.db is untouched."""
    db_path = tmp_path / "empty_fpl.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.close()
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    return db_path


@pytest.fixture
def nonexistent_db(tmp_path, monkeypatch):
    """Points src.db at a path that doesn't exist yet -- exactly what a fresh
    deploy sees, since data/ is gitignored and never shipped with the repo."""
    db_path = tmp_path / "does_not_exist_yet.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    return db_path


def test_dashboard_renders_without_crashing_on_nonexistent_db(nonexistent_db, monkeypatch):
    """A brand new deploy (or a first local run) has no data/fpl.db at all.
    The app must create the schema itself rather than crashing with
    'no such table' before the user ever sees a friendly empty-state message.
    """
    import src.dashboard.refresh as refresh_module

    # No squad snapshot on a brand-new DB now triggers the main data
    # auto-refresh automatically -- mocked here so the test stays fast and
    # network-free rather than actually hitting the live FPL API.
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["mocked"])

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not at.exception, f"Dashboard raised on a brand-new DB: {at.exception}"
    assert nonexistent_db.exists()
    info_texts = " ".join(i.value for i in at.info)
    assert "No squad snapshot yet" in info_texts


def test_dashboard_renders_without_crashing_on_empty_db(empty_db, monkeypatch):
    import streamlit as st
    import src.dashboard.refresh as refresh_module

    st.cache_data.clear()
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["mocked"])

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    assert not at.exception, f"Dashboard raised: {at.exception}"
    # All four sections should show a friendly "no data yet" message rather
    # than crash when the database has no ingested data.
    info_texts = " ".join(i.value for i in at.info)
    assert "No squad snapshot yet" in info_texts
    assert "No transfer recommendation available" in info_texts
    assert "No league pick data yet" in info_texts


def test_refresh_button_status_messages_survive_the_rerun(empty_db, monkeypatch):
    """`refresh_all` triggers `st.rerun()` right after refreshing -- a naive
    `st.write(message)` right before that rerun would never actually be seen,
    since Streamlit discards the current run's output when it reruns. This
    confirms the messages are stashed in session_state and actually shown on
    the following run instead of silently disappearing.
    """
    import streamlit as st
    import src.dashboard.refresh as refresh_module

    st.cache_data.clear()
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["✅ Fake refresh step done."])

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    at.sidebar.button[0].click().run()
    assert not at.exception

    all_text = " ".join(el.value for el in at.get("markdown"))
    assert "Fake refresh step done" in all_text


def test_main_data_auto_refreshes_once_per_session_without_clicking_refresh(empty_db, monkeypatch):
    """No squad snapshot yet should trigger `refresh_all` automatically on
    the very first load -- no manual button click required. Same
    st.rerun()-discards-output hazard as the manual button applies here too.
    """
    import streamlit as st
    import src.dashboard.refresh as refresh_module

    st.cache_data.clear()
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["✅ Fake auto refresh done."])

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception

    all_text = " ".join(el.value for el in at.get("markdown"))
    assert "Fake auto refresh done" in all_text


def test_main_data_does_not_auto_refresh_again_once_already_attempted(empty_db, monkeypatch):
    """Guards against repeatedly hammering the FPL API on every rerun if the
    manager/league ID is wrong and a squad snapshot never actually appears."""
    import streamlit as st
    import src.dashboard.refresh as refresh_module

    st.cache_data.clear()
    calls = []
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: calls.append(1) or ["✅ Fake auto refresh done."])

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert len(calls) == 1

    at.run()
    assert len(calls) == 1


def test_previous_season_stats_auto_fetched_once_when_players_exist_but_none_stored(empty_db, monkeypatch):
    """Regression test: the old Pre-Season Squad tab used to auto-fetch
    previous-season stats the first time it was opened with none stored, but
    that trigger was removed along with the tab itself -- silently orphaning
    the fetch. Without it, `player_previous_season_stats` never gets
    populated and Phase 2's early-season fallback (see
    `src/scoring/projections.py:_previous_season_priors`) never has anything
    to fall back to, so every projection stays stuck at the flat
    no-current-season-data baseline. This confirms the sidebar now triggers
    the fetch itself, once, as soon as there's a player list but no stats.
    """
    import streamlit as st
    import src.dashboard.refresh as refresh_module

    conn = sqlite3.connect(empty_db)
    conn.execute(
        "INSERT INTO players (id, team_id, element_type, web_name, now_cost, status) VALUES (1, 1, 1, 'P1', 45, 'a')"
    )
    conn.commit()
    conn.close()

    st.cache_data.clear()
    calls = []
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["mocked"])
    monkeypatch.setattr(
        refresh_module,
        "refresh_previous_season_stats",
        lambda: calls.append(1) or ["✅ Stored previous-season stats for 1/1 players."],
    )

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    # Isolate this test to the previous-season fetch path -- the main squad
    # auto-refresh is a separate, already-covered trigger.
    at.session_state["auto_refresh_attempted"] = True
    at.run()

    assert not at.exception, f"Dashboard raised: {at.exception}"
    assert len(calls) == 1
    all_text = " ".join(el.value for el in at.get("markdown"))
    assert "Stored previous-season stats for 1/1 players" in all_text

    # And it must not repeat on a later rerun (a ~700-request pull isn't
    # something to silently retry every time the page reruns).
    at.run()
    assert len(calls) == 1


def test_previous_season_stats_retry_button_shown_if_fetch_stored_nothing(empty_db, monkeypatch):
    """If the automatic fetch already ran this session and still stored
    nothing (e.g. the FPL API was briefly unavailable), a manual retry
    button should appear rather than leaving the user stuck with silently
    flat projections and no way to try again without reloading the page."""
    import streamlit as st
    import src.dashboard.refresh as refresh_module

    conn = sqlite3.connect(empty_db)
    conn.execute(
        "INSERT INTO players (id, team_id, element_type, web_name, now_cost, status) VALUES (1, 1, 1, 'P1', 45, 'a')"
    )
    conn.commit()
    conn.close()

    st.cache_data.clear()
    calls = []
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["mocked"])
    monkeypatch.setattr(
        refresh_module,
        "refresh_previous_season_stats",
        lambda: calls.append(1) or ["⚠️ Could not fetch previous-season stats: no network."],
    )

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["auto_refresh_attempted"] = True
    at.session_state["preseason_auto_fetch_attempted"] = True  # simulate the automatic attempt already having run
    at.run()

    assert not at.exception, f"Dashboard raised: {at.exception}"
    assert len(calls) == 0  # not retried automatically just because coverage is still 0

    retry_buttons = [b for b in at.sidebar.button if "Retry fetching previous-season stats" in b.label]
    assert len(retry_buttons) == 1

    retry_buttons[0].click().run()
    assert len(calls) == 1
