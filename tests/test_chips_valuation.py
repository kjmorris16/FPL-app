from src.chips import valuation


def _insert_team(conn, team_id, name="Team"):
    conn.execute("INSERT INTO teams (id, name) VALUES (?, ?)", (team_id, f"{name}{team_id}"))


def _insert_player(conn, player_id, team_id, element_type=4, web_name=None):
    conn.execute(
        "INSERT INTO players (id, team_id, element_type, web_name) VALUES (?, ?, ?, ?)",
        (player_id, team_id, element_type, web_name or f"P{player_id}"),
    )


def _insert_squad_pick(conn, manager_id, gw, player_id, squad_position):
    conn.execute(
        "INSERT INTO my_squad_history (manager_id, gw, player_id, squad_position, is_captain, is_vice_captain, "
        "multiplier, purchase_price, sell_price) VALUES (?, ?, ?, ?, 0, 0, 1, 50, 50)",
        (manager_id, gw, player_id, squad_position),
    )


def _insert_projection(conn, player_id, gw, points):
    conn.execute(
        "INSERT INTO player_projections (player_id, gameweek, projected_points, confidence, computed_at) "
        "VALUES (?, ?, ?, 1.0, '2026-01-01T00:00:00Z')",
        (player_id, gw, points),
    )


def _insert_fixture(conn, fixture_id, event, team_h, team_a, h_diff=3, a_diff=3):
    conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES (?, ?, ?, ?, ?, ?)",
        (fixture_id, event, team_h, team_a, h_diff, a_diff),
    )


def test_bench_boost_value_sums_bench_projections(db_conn):
    _insert_team(db_conn, 1)
    for pid, pos in [(101, 1), (102, 11), (103, 12), (104, 13), (105, 14), (106, 15)]:
        _insert_player(db_conn, pid, 1)
        _insert_squad_pick(db_conn, 1213466, 10, pid, pos)
    for pid, pts in [(103, 2.0), (104, 3.5), (105, 1.0), (106, 0.5)]:
        _insert_projection(db_conn, pid, 10, pts)
    _insert_projection(db_conn, 101, 10, 6.0)  # starter -- must not be counted
    db_conn.commit()

    value = valuation.bench_boost_value(db_conn, 1213466, squad_gw=10, target_gw=10)
    assert value == 2.0 + 3.5 + 1.0 + 0.5


def test_bench_boost_value_zero_when_no_squad(db_conn):
    assert valuation.bench_boost_value(db_conn, 1213466, squad_gw=10, target_gw=10) == 0.0


def test_triple_captain_value_picks_best_starter(db_conn):
    _insert_team(db_conn, 1)
    for pid, pos in [(101, 1), (102, 2), (103, 12)]:
        _insert_player(db_conn, pid, 1)
        _insert_squad_pick(db_conn, 1213466, 10, pid, pos)
    _insert_projection(db_conn, 101, 10, 5.0)
    _insert_projection(db_conn, 102, 10, 9.0)  # best starter
    _insert_projection(db_conn, 103, 10, 20.0)  # bench -- must be ignored
    db_conn.commit()

    gain, best_id = valuation.triple_captain_value(db_conn, 1213466, squad_gw=10, target_gw=10)
    assert best_id == 102
    assert gain == 9.0


def test_triple_captain_value_no_starters_returns_none(db_conn):
    gain, best_id = valuation.triple_captain_value(db_conn, 1213466, squad_gw=10, target_gw=10)
    assert gain == 0.0
    assert best_id is None


def test_wildcard_window_score_counts_good_run_and_dgw_teams(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    # Team 1 starts a good 3-GW run at GW11 (candidate_gw=10 -> run_start=11)
    for gw in range(11, 14):
        _insert_fixture(db_conn, gw, event=gw, team_h=1, team_a=2, h_diff=1, a_diff=5)
    # Team 2 has a DGW at GW12 (within the lookahead window from candidate_gw=10)
    _insert_fixture(db_conn, 100, event=12, team_h=2, team_a=1, h_diff=3, a_diff=3)
    db_conn.commit()

    score, good_run_teams, dgw_teams = valuation.wildcard_window_score(db_conn, start_gw=10, end_gw=16, candidate_gw=10)
    assert 1 in good_run_teams
    assert 2 in dgw_teams
    assert score == len(good_run_teams) + len(dgw_teams)


def test_free_hit_window_score_uses_squad_when_available(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_player(db_conn, 101, 1)
    _insert_player(db_conn, 102, 2)
    _insert_squad_pick(db_conn, 1213466, 10, 101, 1)
    _insert_squad_pick(db_conn, 1213466, 10, 102, 2)
    _insert_team(db_conn, 3)
    # Only teams 1 and 3 play in GW12 -- team 2 (player 102's team) blanks
    db_conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES (1, 12, 1, 3, 3, 3)"
    )
    db_conn.commit()

    score = valuation.free_hit_window_score(db_conn, 1213466, squad_gw=10, candidate_gw=12)
    assert score == 1  # exactly player 102's team (2) blanks


def test_free_hit_window_score_falls_back_to_team_count_without_squad(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_team(db_conn, 3)
    db_conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES (1, 12, 1, 3, 3, 3)"
    )
    db_conn.commit()

    score = valuation.free_hit_window_score(db_conn, 1213466, squad_gw=None, candidate_gw=12)
    assert score == 1  # team 2 blanks leaguewide


def test_free_hit_window_score_zero_when_no_blanks(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    db_conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES (1, 12, 1, 2, 3, 3)"
    )
    db_conn.commit()
    assert valuation.free_hit_window_score(db_conn, 1213466, squad_gw=10, candidate_gw=12) == 0
