import sqlite3

import pytest

import src.db as db_module
from src.dashboard import refresh as dash_refresh
from src.db import SCHEMA


@pytest.fixture
def db_with_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "fpl.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.close()
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    return db_path


def test_refresh_previous_season_stats_warns_when_no_players(db_with_schema, monkeypatch):
    called = False

    def fake_fetch(conn, player_ids):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(dash_refresh.previous_season_ingest, "fetch_previous_season_stats", fake_fetch)

    messages = dash_refresh.refresh_previous_season_stats()

    assert not called  # must not even try the API when there are no players yet
    assert any("Refresh data" in m for m in messages)


def test_refresh_previous_season_stats_success(db_with_schema, monkeypatch):
    conn = sqlite3.connect(db_with_schema)
    conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'Striker')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(dash_refresh.previous_season_ingest, "fetch_previous_season_stats", lambda conn, player_ids: len(player_ids))

    messages = dash_refresh.refresh_previous_season_stats()

    assert any("Stored previous-season stats for 1/1 players" in m for m in messages)


def test_refresh_previous_season_stats_handles_exception_gracefully(db_with_schema, monkeypatch):
    conn = sqlite3.connect(db_with_schema)
    conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'Striker')")
    conn.commit()
    conn.close()

    def raise_error(conn, player_ids):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(dash_refresh.previous_season_ingest, "fetch_previous_season_stats", raise_error)

    messages = dash_refresh.refresh_previous_season_stats()

    assert any("Could not fetch previous-season stats" in m for m in messages)
