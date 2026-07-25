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


def test_dashboard_renders_without_crashing_on_nonexistent_db(nonexistent_db):
    """A brand new deploy (or a first local run) has no data/fpl.db at all.
    The app must create the schema itself rather than crashing with
    'no such table' before the user ever sees a friendly empty-state message.
    """
    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
    at.run()

    assert not at.exception, f"Dashboard raised on a brand-new DB: {at.exception}"
    assert nonexistent_db.exists()
    info_texts = " ".join(i.value for i in at.info)
    assert "No squad snapshot yet" in info_texts


def test_dashboard_renders_without_crashing_on_empty_db(empty_db):
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


def test_refresh_button_status_messages_survive_the_rerun(empty_db, monkeypatch):
    """`refresh_all` triggers `st.rerun()` right after refreshing -- a naive
    `st.write(message)` right before that rerun would never actually be seen,
    since Streamlit discards the current run's output when it reruns. This
    confirms the messages are stashed in session_state and actually shown on
    the following run instead of silently disappearing.
    """
    import src.dashboard.refresh as refresh_module

    monkeypatch.setattr(refresh_module, "refresh_all", lambda manager_id, league_id: ["✅ Fake refresh step done."])

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
    at.run()
    assert not at.exception

    at.sidebar.button[0].click().run()
    assert not at.exception

    all_text = " ".join(el.value for el in at.get("markdown"))
    assert "Fake refresh step done" in all_text


def test_preseason_fetch_button_status_messages_survive_the_rerun(empty_db, monkeypatch):
    """Same st.rerun()-discards-output hazard as the sidebar refresh button,
    for the Pre-Season tab's separate "Fetch previous-season stats" button.
    """
    import src.dashboard.refresh as refresh_module

    monkeypatch.setattr(refresh_module, "refresh_previous_season_stats", lambda: ["✅ Fake previous-season fetch done."])

    at = AppTest.from_file("src/dashboard/app.py", default_timeout=30)
    at.run()
    assert not at.exception

    fetch_button = next(b for b in at.button if b.label == "📥 Fetch previous-season stats")
    fetch_button.click().run()
    assert not at.exception

    all_text = " ".join(el.value for el in at.get("markdown"))
    assert "Fake previous-season fetch done" in all_text
