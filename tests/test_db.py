def test_schema_creates_expected_tables(db_conn):
    tables = {
        row["name"]
        for row in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"teams", "events", "players", "fixtures", "gameweek_stats"} <= tables


def test_gameweek_stats_primary_key_prevents_duplicate_player_gw(db_conn):
    db_conn.execute(
        "INSERT INTO teams (id, name) VALUES (1, 'Arsenal')"
    )
    db_conn.execute(
        "INSERT INTO players (id, team_id, web_name) VALUES (101, 1, 'Saka')"
    )
    db_conn.execute(
        "INSERT INTO gameweek_stats (player_id, gw, total_points) VALUES (101, 1, 10)"
    )
    db_conn.commit()

    row = db_conn.execute(
        "SELECT * FROM gameweek_stats WHERE player_id = 101 AND gw = 1"
    ).fetchone()
    assert row["total_points"] == 10
