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


def test_refresh_all_computes_projections_across_the_full_chip_planning_window(db_with_schema, monkeypatch):
    """Regression test: projections used to only be computed 5 gameweeks
    ahead, while the Chip Timing tab plans 10 gameweeks ahead
    (chip_constants.PLANNING_HORIZON_GWS) -- Bench Boost/Triple Captain
    silently showed 0.0 past that 5-GW cutoff, even for a gameweek the
    calendar correctly flagged as a double gameweek in its own notes, so the
    "best week" recommendation could completely miss a real double/blank
    gameweek that fell in gameweeks 6-10. refresh_all's projection horizon
    must cover at least the chip planner's full window.
    """
    from src.chips import constants as chip_constants

    conn = sqlite3.connect(db_with_schema)
    conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost, status) VALUES (101, 1, 4, 'Striker', 100, 'a')")
    conn.commit()
    conn.close()

    # No network calls -- only the projection-computation step is real.
    monkeypatch.setattr(dash_refresh, "ingest_refresh", type("_", (), {"run": staticmethod(lambda with_history=False: None)}))
    monkeypatch.setattr(dash_refresh.manager_ingest, "fetch_squad_snapshot", lambda conn, manager_id: None)
    monkeypatch.setattr(dash_refresh.manager_ingest, "fetch_chip_usage", lambda conn, manager_id: [])
    monkeypatch.setattr(dash_refresh.differentials_ingestion, "fetch_league_managers", lambda conn, league_id: None)
    monkeypatch.setattr(dash_refresh.differentials_ingestion, "fetch_league_picks", lambda conn, league_id: None)

    dash_refresh.refresh_all(manager_id=1213466, league_id=1)

    conn = sqlite3.connect(db_with_schema)
    conn.row_factory = sqlite3.Row
    stored_gws = {row["gameweek"] for row in conn.execute("SELECT DISTINCT gameweek FROM player_projections")}
    conn.close()

    assert max(stored_gws) - min(stored_gws) + 1 >= chip_constants.PLANNING_HORIZON_GWS
