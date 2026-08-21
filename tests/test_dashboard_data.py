import sqlite3

import pytest
import streamlit as st

import src.db as db_module
from src.dashboard import data as dash_data
from src.db import SCHEMA


@pytest.fixture
def db_with_schema(tmp_path, monkeypatch):
    """Points src.db at a fresh SQLite file for the duration of the test, so
    the dashboard's real data/fpl.db is untouched, and clears
    st.cache_data so a result cached against a previous test's DB can't
    leak in here."""
    db_path = tmp_path / "fpl.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.close()
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    st.cache_data.clear()
    return db_path


def test_load_transfer_recommendation_captain_comes_from_actual_current_squad(db_with_schema):
    """Regression test: the captain/vice-captain used to be picked from the
    squad you'd have *after* making the top recommended transfer, not the
    squad you actually own right now -- so it could recommend captaining a
    player you haven't transferred in yet, which isn't something you can
    actually act on. Reproduces that exact scenario: a transfer is
    recommended (swap a weak bench GK for a much-better-projected one), but
    the true best captain is already in the current squad at a different
    position.
    """
    conn = sqlite3.connect(db_with_schema)
    manager_id = 1213466
    gw = 10

    for team_id in range(1, 8):
        conn.execute("INSERT INTO teams (id, name, short_name) VALUES (?, ?, ?)", (team_id, f"Team{team_id}", f"T{team_id}"))

    # Spread across teams 1-6 (max 3 per team, a legal squad), positions 2/5/5/3.
    squad_players = [
        (101, 1, 1, 45), (102, 2, 1, 40),
        (111, 1, 2, 45), (112, 2, 2, 45), (113, 3, 2, 45), (114, 4, 2, 45), (115, 5, 2, 45),
        (121, 1, 3, 55), (122, 2, 3, 55), (123, 3, 3, 55), (124, 4, 3, 55), (125, 5, 3, 55),
        (131, 3, 4, 60), (132, 4, 4, 60), (133, 6, 4, 60),  # 133 is the true best captain option
    ]
    for i, (pid, team_id, et, cost) in enumerate(squad_players):
        conn.execute(
            "INSERT INTO players (id, team_id, element_type, web_name, now_cost, status) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, team_id, et, f"P{pid}", cost, "a"),
        )
        conn.execute(
            "INSERT INTO my_squad_history (manager_id, gw, player_id, squad_position, is_captain, is_vice_captain, "
            "multiplier, purchase_price, sell_price) VALUES (?, ?, ?, ?, 0, 0, 1, ?, ?)",
            (manager_id, gw, pid, i + 1, cost, cost),
        )
    conn.execute(
        "INSERT INTO my_manager_snapshot (manager_id, gw, bank, squad_value, free_transfers) VALUES (?, ?, 20, 750, 1)",
        (manager_id, gw),
    )
    # A cheap, much-better-projected GK not currently owned -- the optimizer
    # correctly suggests swapping the weak bench GK for them.
    conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost, status) VALUES (201, 7, 1, 'NewGK', 40, 'a')")

    projections = {
        101: 3.0, 102: 1.0,
        111: 4.0, 112: 4.0, 113: 4.0, 114: 4.0, 115: 4.0,
        121: 6.0, 122: 6.0, 123: 6.0, 124: 6.0, 125: 6.0,
        131: 7.0, 132: 7.0, 133: 9.0,
        201: 9.5,
    }
    for pid, pts in projections.items():
        conn.execute(
            "INSERT INTO player_projections (player_id, gameweek, projected_points, confidence, computed_at) VALUES (?, ?, ?, 1.0, '2026-01-01T00:00:00Z')",
            (pid, gw, pts),
        )
    conn.commit()
    conn.close()

    rec = dash_data.load_transfer_recommendation(manager_id)
    assert rec is not None
    assert len(rec["top_combo"].swaps) == 1  # sanity: a transfer really is recommended this week
    assert rec["top_combo"].swaps[0].in_player["web_name"] == "NewGK"

    assert rec["captain"] == "P133"  # the best captain from the squad actually owned
    assert rec["captain"] != "NewGK"  # not the not-yet-transferred-in player
    assert rec["captain_rationale"] is not None
