import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

import src.db as db_module
from src.db import SCHEMA


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

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
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

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
    at.run()

    assert not at.exception, f"Dashboard raised: {at.exception}"
    # All five sections should show a friendly "no data yet" message rather
    # than crash when the database has no ingested data.
    info_texts = " ".join(i.value for i in at.info)
    assert "No squad snapshot yet" in info_texts
    assert "No transfer recommendation available" in info_texts
    assert "No league pick data yet" in info_texts
    assert "No previous-season stats ingested yet" in info_texts

    # The data-coverage diagnostic should be visible even with an empty DB,
    # so a silent 0-rows-stored failure is never mistaken for "the squad
    # optimizer is just being weird".
    caption_texts = " ".join(c.value for c in at.get("caption"))
    assert "Data coverage: 0/0 current players" in caption_texts


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

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
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

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
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

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
    at.run()
    assert not at.exception
    assert len(calls) == 1

    at.run()
    assert len(calls) == 1


def test_preseason_auto_fetches_previous_season_stats_on_first_load(empty_db, monkeypatch):
    """The Pre-Season tab fetches previous-season stats automatically the
    first time it loads with players present but no stats stored -- no
    button click required. Same st.rerun()-discards-output hazard as the
    sidebar refresh button applies here too, since the auto-fetch triggers
    its own rerun.
    """
    import streamlit as st
    import src.dashboard.refresh as refresh_module

    conn = sqlite3.connect(empty_db)
    conn.execute("INSERT INTO players (id, team_id, web_name, element_type, now_cost) VALUES (1, 1, 'Test Player', 3, 50)")
    conn.commit()
    conn.close()
    # `load_preseason_coverage` is cached process-wide by st.cache_data --
    # without clearing it, a 0/0 result cached by an earlier test (against a
    # different empty DB) can leak in here and make the guard below think
    # there's nothing to fetch.
    st.cache_data.clear()

    # No squad snapshot here either, so the main data auto-refresh also
    # fires this run -- mocked so the test stays fast and network-free.
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["mocked"])
    monkeypatch.setattr(refresh_module, "refresh_previous_season_stats", lambda: ["✅ Fake previous-season fetch done."])

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
    at.run()
    assert not at.exception

    all_text = " ".join(el.value for el in at.get("markdown"))
    assert "Fake previous-season fetch done" in all_text


def test_preseason_does_not_auto_fetch_again_once_already_attempted(empty_db, monkeypatch):
    """Guards against repeatedly hammering the ~700-request fetch on every
    rerun if it comes back having stored nothing."""
    import streamlit as st
    import src.dashboard.refresh as refresh_module

    conn = sqlite3.connect(empty_db)
    conn.execute("INSERT INTO players (id, team_id, web_name, element_type, now_cost) VALUES (1, 1, 'Test Player', 3, 50)")
    conn.commit()
    conn.close()
    # `load_preseason_coverage` is cached process-wide by st.cache_data --
    # without clearing it, a 0/0 result cached by an earlier test (against a
    # different empty DB) can leak in here and make the guard below think
    # there's nothing to fetch.
    st.cache_data.clear()

    # No squad snapshot here either, so the main data auto-refresh also
    # fires this run -- mocked so the test stays fast and network-free.
    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["mocked"])
    calls = []
    monkeypatch.setattr(refresh_module, "refresh_previous_season_stats", lambda: calls.append(1) or ["✅ Fake fetch done."])

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
    at.run()
    assert not at.exception
    assert len(calls) == 1

    # A further interaction (any rerun) shouldn't trigger a second auto-fetch.
    at.run()
    assert len(calls) == 1

    assert any("Retry fetching previous-season stats" in b.label for b in at.button)
