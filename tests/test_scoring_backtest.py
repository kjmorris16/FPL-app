from src.scoring import backtest, constants as c


def test_pearson_correlation_perfect_positive():
    assert round(backtest._pearson_correlation([1, 2, 3], [2, 4, 6]), 6) == 1.0


def test_pearson_correlation_perfect_negative():
    assert round(backtest._pearson_correlation([1, 2, 3], [6, 4, 2]), 6) == -1.0


def test_pearson_correlation_insufficient_data():
    assert backtest._pearson_correlation([1], [1]) is None


def test_pearson_correlation_zero_variance_is_none():
    assert backtest._pearson_correlation([1, 1, 1], [1, 2, 3]) is None


def test_mean_absolute_error():
    assert backtest._mean_absolute_error([1, 2, 3], [1, 4, 6]) == (0 + 2 + 3) / 3


def test_mean_absolute_error_empty():
    assert backtest._mean_absolute_error([], []) is None


def _insert_team(conn, team_id, name):
    conn.execute("INSERT INTO teams (id, name) VALUES (?, ?)", (team_id, name))


def _insert_player(conn, player_id, team_id, element_type, web_name):
    conn.execute(
        "INSERT INTO players (id, team_id, element_type, web_name, status) VALUES (?, ?, ?, ?, 'a')",
        (player_id, team_id, element_type, web_name),
    )


def _insert_fixture(conn, fixture_id, event, team_h, team_a):
    conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) "
        "VALUES (?, ?, ?, ?, 3, 3)",
        (fixture_id, event, team_h, team_a),
    )


def _insert_gw_stat(conn, player_id, gw, total_points, minutes=90, expected_goals=0.3):
    conn.execute(
        "INSERT INTO gameweek_stats (player_id, gw, total_points, minutes, expected_goals) "
        "VALUES (?, ?, ?, ?, ?)",
        (player_id, gw, total_points, minutes, expected_goals),
    )


def test_run_backtest_does_not_look_ahead(db_conn):
    _insert_team(db_conn, 1, "Home United")
    _insert_team(db_conn, 2, "Away FC")
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Striker")

    for gw in range(1, 6):
        _insert_fixture(db_conn, gw, event=gw, team_h=1, team_a=2)
        _insert_gw_stat(db_conn, 101, gw, total_points=2, expected_goals=0.1)

    _insert_fixture(db_conn, 6, event=6, team_h=1, team_a=2)
    _insert_gw_stat(db_conn, 101, 6, total_points=2, expected_goals=0.1)
    db_conn.commit()

    pairs, _ = backtest.run_backtest(db_conn, start_gw=6, end_gw=6)
    projected_gw6 = next(p[2] for p in pairs if p[0] == 101)

    # Rewrite GW6's own actual result to a huge outlier. If the model used
    # this row to build GW6's projection (look-ahead bias), the projection
    # would change; since it's computed as-of GW6 (gw < 6 only), it must not.
    db_conn.execute(
        "UPDATE gameweek_stats SET total_points = 50, expected_goals = 10.0 WHERE player_id = 101 AND gw = 6"
    )
    db_conn.commit()

    pairs_again, _ = backtest.run_backtest(db_conn, start_gw=6, end_gw=6)
    projected_gw6_again = next(p[2] for p in pairs_again if p[0] == 101)

    assert projected_gw6 == projected_gw6_again


def test_run_backtest_reports_metrics(db_conn):
    _insert_team(db_conn, 1, "Home United")
    _insert_team(db_conn, 2, "Away FC")
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Striker")

    for gw in range(1, 9):
        _insert_fixture(db_conn, gw, event=gw, team_h=1, team_a=2)
        _insert_gw_stat(db_conn, 101, gw, total_points=6, expected_goals=0.5)
    db_conn.commit()

    pairs, metrics = backtest.run_backtest(db_conn, start_gw=7, end_gw=8)
    assert metrics["n"] == len(pairs) == 2
    assert metrics["mae"] is not None
