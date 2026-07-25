from src.ingest import refresh

SAMPLE_TEAMS = [
    {
        "id": 1,
        "name": "Arsenal",
        "short_name": "ARS",
        "strength": 4,
        "strength_overall_home": 1200,
        "strength_overall_away": 1250,
        "strength_attack_home": 1200,
        "strength_attack_away": 1250,
        "strength_defence_home": 1200,
        "strength_defence_away": 1250,
    },
    {
        "id": 2,
        "name": "Bournemouth",
        "short_name": "BOU",
        "strength": 3,
        "strength_overall_home": 1050,
        "strength_overall_away": 1000,
        "strength_attack_home": 1050,
        "strength_attack_away": 1000,
        "strength_defence_home": 1050,
        "strength_defence_away": 1000,
    },
]

SAMPLE_EVENTS = [
    {
        "id": 1,
        "name": "Gameweek 1",
        "deadline_time": "2026-08-14T17:30:00Z",
        "finished": True,
        "is_previous": True,
        "is_current": False,
        "is_next": False,
        "average_entry_score": 55,
        "highest_score": 130,
    },
    {
        "id": 2,
        "name": "Gameweek 2",
        "deadline_time": "2026-08-21T17:30:00Z",
        "finished": False,
        "is_previous": False,
        "is_current": True,
        "is_next": False,
        "average_entry_score": None,
        "highest_score": None,
    },
]

SAMPLE_PLAYERS = [
    {
        "id": 101,
        "team": 1,
        "first_name": "Bukayo",
        "second_name": "Saka",
        "web_name": "Saka",
        "element_type": 3,
        "now_cost": 100,
        "selected_by_percent": "45.2",
        "form": "5.5",
        "total_points": 60,
        "minutes": 540,
        "goals_scored": 4,
        "assists": 3,
        "clean_sheets": 2,
        "goals_conceded": 4,
        "expected_goals": "3.21",
        "expected_assists": "2.87",
        "expected_goal_involvements": "6.08",
        "expected_goals_conceded": "3.90",
        "ict_index": "120.5",
        "influence": "300.2",
        "creativity": "250.1",
        "threat": "400.0",
        "bonus": 8,
        "bps": 210,
        "status": "a",
        "chance_of_playing_next_round": None,
        "chance_of_playing_this_round": None,
        "points_per_game": "10.0",
        "value_season": "6.0",
    }
]

SAMPLE_FIXTURES = [
    {
        "id": 1001,
        "event": 1,
        "team_h": 1,
        "team_a": 2,
        "team_h_score": 2,
        "team_a_score": 0,
        "kickoff_time": "2026-08-16T14:00:00Z",
        "finished": True,
        "team_h_difficulty": 2,
        "team_a_difficulty": 4,
    }
]


def test_refresh_teams(db_conn):
    refresh.refresh_teams(db_conn, SAMPLE_TEAMS, "2026-07-25T00:00:00Z")
    rows = db_conn.execute("SELECT * FROM teams ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["name"] == "Arsenal"
    assert rows[1]["short_name"] == "BOU"


def test_refresh_teams_upsert_updates_existing_row(db_conn):
    refresh.refresh_teams(db_conn, SAMPLE_TEAMS, "2026-07-25T00:00:00Z")
    updated = [{**SAMPLE_TEAMS[0], "strength": 5}]
    refresh.refresh_teams(db_conn, updated, "2026-07-26T00:00:00Z")
    rows = db_conn.execute("SELECT * FROM teams").fetchall()
    assert len(rows) == 2
    row = db_conn.execute("SELECT * FROM teams WHERE id = 1").fetchone()
    assert row["strength"] == 5
    assert row["pulled_at"] == "2026-07-26T00:00:00Z"


def test_refresh_events(db_conn):
    refresh.refresh_events(db_conn, SAMPLE_EVENTS, "2026-07-25T00:00:00Z")
    rows = db_conn.execute("SELECT * FROM events ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["finished"] == 1
    assert rows[1]["is_current"] == 1


def test_refresh_players_converts_string_stats_to_float(db_conn):
    refresh.refresh_teams(db_conn, SAMPLE_TEAMS, "2026-07-25T00:00:00Z")
    refresh.refresh_players(db_conn, SAMPLE_PLAYERS, "2026-07-25T00:00:00Z")
    row = db_conn.execute("SELECT * FROM players WHERE id = 101").fetchone()
    assert row["web_name"] == "Saka"
    assert row["selected_by_percent"] == 45.2
    assert row["expected_goal_involvements"] == 6.08
    assert row["team_id"] == 1


def test_refresh_fixtures(db_conn):
    refresh.refresh_teams(db_conn, SAMPLE_TEAMS, "2026-07-25T00:00:00Z")
    refresh.refresh_fixtures(db_conn, SAMPLE_FIXTURES, "2026-07-25T00:00:00Z")
    row = db_conn.execute("SELECT * FROM fixtures WHERE id = 1001").fetchone()
    assert row["team_h"] == 1
    assert row["team_a_difficulty"] == 4
    assert row["finished"] == 1


def test_refresh_gameweek_history_uses_element_summary(db_conn, monkeypatch):
    refresh.refresh_teams(db_conn, SAMPLE_TEAMS, "2026-07-25T00:00:00Z")
    refresh.refresh_players(db_conn, SAMPLE_PLAYERS, "2026-07-25T00:00:00Z")

    def fake_get_element_summary(player_id):
        return {
            "history": [
                {
                    "round": 1,
                    "fixture": 1001,
                    "opponent_team": 2,
                    "was_home": True,
                    "total_points": 12,
                    "minutes": 90,
                    "goals_scored": 1,
                    "assists": 1,
                    "clean_sheets": 1,
                    "goals_conceded": 0,
                    "expected_goals": "0.55",
                    "expected_assists": "0.30",
                    "expected_goal_involvements": "0.85",
                    "expected_goals_conceded": "0.40",
                    "bps": 35,
                    "bonus": 3,
                    "influence": "50.0",
                    "creativity": "40.0",
                    "threat": "60.0",
                    "ict_index": "15.0",
                    "value": 100,
                }
            ]
        }

    monkeypatch.setattr(refresh.api_client, "get_element_summary", fake_get_element_summary)

    refresh.refresh_gameweek_history(db_conn, [101], "2026-07-25T00:00:00Z")

    row = db_conn.execute("SELECT * FROM gameweek_stats WHERE player_id = 101 AND gw = 1").fetchone()
    assert row is not None
    assert row["total_points"] == 12
    assert row["expected_goal_involvements"] == 0.85


def test_refresh_gameweek_history_skips_player_on_error(db_conn, monkeypatch, caplog):
    refresh.refresh_teams(db_conn, SAMPLE_TEAMS, "2026-07-25T00:00:00Z")
    refresh.refresh_players(db_conn, SAMPLE_PLAYERS, "2026-07-25T00:00:00Z")

    def fake_get_element_summary(player_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(refresh.api_client, "get_element_summary", fake_get_element_summary)

    refresh.refresh_gameweek_history(db_conn, [101], "2026-07-25T00:00:00Z")

    rows = db_conn.execute("SELECT * FROM gameweek_stats").fetchall()
    assert len(rows) == 0
