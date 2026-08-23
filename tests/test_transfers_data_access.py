from src.transfers import data_access


def test_get_latest_squad_gw_returns_none_when_no_snapshot(db_conn):
    assert data_access.get_latest_squad_gw(db_conn, manager_id=999) is None


def test_get_latest_squad_gw_returns_max_gw(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'Sharpe')")
    db_conn.execute(
        "INSERT INTO my_squad_history (manager_id, gw, player_id) VALUES (1213466, 8, 101), (1213466, 10, 101)"
    )
    db_conn.commit()
    assert data_access.get_latest_squad_gw(db_conn, manager_id=1213466) == 10


def test_get_manager_snapshot(db_conn):
    db_conn.execute(
        "INSERT INTO my_manager_snapshot (manager_id, gw, bank, squad_value, free_transfers) "
        "VALUES (1213466, 10, 15, 1000, 2)"
    )
    db_conn.commit()
    snapshot = data_access.get_manager_snapshot(db_conn, 1213466, 10)
    assert snapshot["bank"] == 15
    assert snapshot["free_transfers"] == 2


def test_get_manager_snapshot_missing_returns_none(db_conn):
    assert data_access.get_manager_snapshot(db_conn, 1213466, 10) is None


def _seed_squad(conn):
    conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost, status) VALUES (101, 1, 4, 'Sharpe', 90, 'a')")
    conn.execute(
        "INSERT INTO my_squad_history (manager_id, gw, player_id, squad_position, is_captain, is_vice_captain, "
        "multiplier, purchase_price, sell_price) VALUES (1213466, 10, 101, 1, 1, 0, 2, 80, 85)"
    )
    conn.commit()


def test_get_current_squad_joins_player_fields(db_conn):
    _seed_squad(db_conn)
    squad = data_access.get_current_squad(db_conn, 1213466, 10)
    assert len(squad) == 1
    player = squad[0]
    assert player["web_name"] == "Sharpe"
    assert player["element_type"] == 4
    assert player["sell_price"] == 85
    assert player["is_captain"] == 1


def test_get_candidate_pool_returns_all_players(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost) VALUES (101, 1, 4, 'Sharpe', 90)")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost) VALUES (102, 1, 2, 'Backman', 50)")
    db_conn.commit()
    pool = data_access.get_candidate_pool(db_conn)
    assert {p["player_id"] for p in pool} == {101, 102}


def test_get_projection_totals_sums_across_horizon(db_conn):
    now = "2026-01-01T00:00:00Z"
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'Sharpe')")
    db_conn.executemany(
        "INSERT INTO player_projections (player_id, gameweek, projected_points, confidence, computed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [(101, 10, 5.0, 0.8, now), (101, 11, 3.0, 0.8, now), (101, 12, 4.0, 0.8, now)],
    )
    db_conn.commit()

    totals = data_access.get_projection_totals(db_conn, [101], start_gw=10, horizons=(1, 3))
    assert totals[101][1] == 5.0
    assert totals[101][3] == 12.0


def test_get_projection_totals_missing_player_defaults_to_zero(db_conn):
    totals = data_access.get_projection_totals(db_conn, [999], start_gw=10, horizons=(1,))
    assert totals[999][1] == 0.0


def test_get_average_fixture_difficulty(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home'), (2, 'Away'), (3, 'Third')")
    db_conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES "
        "(1, 10, 1, 2, 2, 4), (2, 11, 3, 1, 3, 5)"
    )
    db_conn.commit()
    # Team 1 is home in fixture 1 (difficulty 2) and away in fixture 2 (difficulty 5)
    avg = data_access.get_average_fixture_difficulty(db_conn, team_id=1, start_gw=10, num_gws=2)
    assert avg == 3.5


def test_get_average_fixture_difficulty_no_fixtures_returns_none(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home')")
    db_conn.commit()
    assert data_access.get_average_fixture_difficulty(db_conn, team_id=1, start_gw=10, num_gws=2) is None


def test_upsert_squad_weakness_stores_and_orders_by_rank(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'Sharpe'), (102, 1, 4, 'Weakling')")
    db_conn.commit()
    now = "2026-01-01T00:00:00Z"
    rows = [
        (1213466, 10, 101, 1.0, 0.2, 0.1, 0.0, 0.6, 2, now),
        (1213466, 10, 102, 4.0, 1.0, 0.5, 0.3, 2.6, 1, now),
    ]
    data_access.upsert_squad_weakness(db_conn, rows)
    db_conn.commit()

    stored = data_access.get_squad_weakness(db_conn, 1213466, 10)
    assert [r["player_id"] for r in stored] == [102, 101]  # ordered by weakness_rank
    assert stored[0]["weakness_score"] == 2.6


def test_upsert_squad_weakness_overwrites_on_conflict(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'Sharpe')")
    db_conn.commit()
    now = "2026-01-01T00:00:00Z"
    data_access.upsert_squad_weakness(db_conn, [(1213466, 10, 101, 1.0, 0.2, 0.1, 0.0, 0.6, 1, now)])
    data_access.upsert_squad_weakness(db_conn, [(1213466, 10, 101, 2.0, 0.4, 0.2, 0.0, 1.2, 1, now)])
    db_conn.commit()

    stored = data_access.get_squad_weakness(db_conn, 1213466, 10)
    assert len(stored) == 1
    assert stored[0]["weakness_score"] == 1.2
