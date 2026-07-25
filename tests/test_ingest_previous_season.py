from src.ingest import previous_season


def _seed_players(conn, player_ids):
    conn.execute("INSERT OR IGNORE INTO teams (id, name) VALUES (1, 'Filler United')")
    conn.executemany(
        "INSERT INTO players (id, team_id, element_type, web_name) VALUES (?, 1, 4, ?)",
        [(pid, f"P{pid}") for pid in player_ids],
    )


def test_fetch_previous_season_stats_stores_last_entry(db_conn, monkeypatch):
    _seed_players(db_conn, [101])

    def fake_get_element_summary(player_id):
        return {
            "history_past": [
                {"season_name": "2023/24", "minutes": 1000, "total_points": 80, "expected_goals": "3.0"},
                {"season_name": "2024/25", "minutes": 2500, "total_points": 180, "goals_scored": 15,
                 "assists": 8, "clean_sheets": 0, "expected_goals": "14.50", "expected_assists": "7.20",
                 "expected_goal_involvements": "21.70", "saves": 0, "bonus": 20, "start_cost": 75, "end_cost": 90},
            ]
        }

    monkeypatch.setattr(previous_season.api_client, "get_element_summary", fake_get_element_summary)

    stored = previous_season.fetch_previous_season_stats(db_conn, [101])
    db_conn.commit()

    assert stored == 1
    row = db_conn.execute("SELECT * FROM player_previous_season_stats WHERE player_id = 101").fetchone()
    assert row["season_name"] == "2024/25"  # the LAST entry, not the first
    assert row["minutes"] == 2500
    assert row["expected_goals"] == 14.5
    assert row["start_cost"] == 75
    assert row["end_cost"] == 90


def test_fetch_previous_season_stats_skips_player_with_no_history(db_conn, monkeypatch):
    _seed_players(db_conn, [101])
    monkeypatch.setattr(previous_season.api_client, "get_element_summary", lambda player_id: {"history_past": []})

    stored = previous_season.fetch_previous_season_stats(db_conn, [101])
    db_conn.commit()

    assert stored == 0
    assert db_conn.execute("SELECT * FROM player_previous_season_stats").fetchall() == []


def test_fetch_previous_season_stats_skips_player_on_error(db_conn, monkeypatch):
    _seed_players(db_conn, [101, 102])

    def fake_get_element_summary(player_id):
        if player_id == 101:
            raise RuntimeError("404")
        return {"history_past": [{"season_name": "2024/25", "minutes": 1800, "total_points": 100}]}

    monkeypatch.setattr(previous_season.api_client, "get_element_summary", fake_get_element_summary)

    stored = previous_season.fetch_previous_season_stats(db_conn, [101, 102])
    db_conn.commit()

    assert stored == 1
    assert db_conn.execute("SELECT * FROM player_previous_season_stats WHERE player_id = 101").fetchall() == []
    assert db_conn.execute("SELECT * FROM player_previous_season_stats WHERE player_id = 102").fetchone() is not None


def test_fetch_previous_season_stats_upsert(db_conn, monkeypatch):
    _seed_players(db_conn, [101])
    monkeypatch.setattr(
        previous_season.api_client, "get_element_summary",
        lambda player_id: {"history_past": [{"season_name": "2024/25", "minutes": 1000, "total_points": 50}]},
    )
    previous_season.fetch_previous_season_stats(db_conn, [101])

    monkeypatch.setattr(
        previous_season.api_client, "get_element_summary",
        lambda player_id: {"history_past": [{"season_name": "2024/25", "minutes": 2000, "total_points": 120}]},
    )
    previous_season.fetch_previous_season_stats(db_conn, [101])
    db_conn.commit()

    rows = db_conn.execute("SELECT * FROM player_previous_season_stats WHERE player_id = 101").fetchall()
    assert len(rows) == 1
    assert rows[0]["minutes"] == 2000
