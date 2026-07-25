from src.differentials import finder


def _seed_team_and_players(conn, players):
    conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Filler United')")
    conn.executemany(
        "INSERT INTO players (id, team_id, element_type, web_name) VALUES (?, 1, 4, ?)",
        [(pid, f"P{pid}") for pid in players],
    )


def _insert_projection(conn, player_id, gw, points):
    conn.execute(
        "INSERT INTO player_projections (player_id, gameweek, projected_points, confidence, computed_at) "
        "VALUES (?, ?, ?, 1.0, '2026-01-01T00:00:00Z')",
        (player_id, gw, points),
    )


def _pick(conn, league_id, manager_id, gw, player_id, is_captain=False):
    conn.execute(
        "INSERT INTO league_manager_picks (league_id, manager_id, gw, player_id, is_captain) VALUES (?, ?, ?, ?, ?)",
        (league_id, manager_id, gw, player_id, int(is_captain)),
    )


def test_differential_score_zero_ownership_scores_full_points():
    assert finder.differential_score(20.0, 0.0) == 20.0


def test_differential_score_full_ownership_scores_zero():
    assert finder.differential_score(20.0, 100.0) == 0.0


def test_differential_score_partial_ownership_scales_linearly():
    assert finder.differential_score(10.0, 25.0) == 7.5


def _seed_scenario(conn, league_id=103056, gw=10):
    _seed_team_and_players(conn, [101, 102, 103, 104])
    # 101: unowned, big projection (best differential)
    # 102: fully owned (all 4 managers), decent projection
    # 103: owned only by manager 1 (25%), medium projection -- and I AM manager 1
    # 104: unowned, small projection
    for pid, pts in [(101, 20.0), (102, 15.0), (103, 10.0), (104, 2.0)]:
        _insert_projection(conn, pid, gw, pts)
        for extra_gw in range(gw + 1, gw + 5):
            _insert_projection(conn, pid, extra_gw, 0.0)

    for manager_id in (1, 2, 3, 4):
        _pick(conn, league_id, manager_id, gw, 102)
    _pick(conn, league_id, 1, gw, 103)

    # My squad snapshot: manager 1 owns player 103
    conn.execute(
        "INSERT INTO my_squad_history (manager_id, gw, player_id, squad_position, is_captain, is_vice_captain, "
        "multiplier, purchase_price, sell_price) VALUES (1, ?, 103, 1, 0, 0, 1, 50, 50)",
        (gw,),
    )
    conn.commit()


def test_build_differential_table_defaults_unowned_players_to_zero(db_conn):
    _seed_scenario(db_conn)
    table = finder.build_differential_table(db_conn, 103056, league_gw=10, start_gw=10, max_ownership_pct=100.0)
    row_101 = next(r for r in table if r["player_id"] == 101)
    assert row_101["ownership_pct"] == 0.0
    assert row_101["differential_score"] == 20.0


def test_build_differential_table_filters_by_max_ownership(db_conn):
    _seed_scenario(db_conn)
    table = finder.build_differential_table(db_conn, 103056, league_gw=10, start_gw=10, max_ownership_pct=30.0)
    player_ids = {r["player_id"] for r in table}
    assert 102 not in player_ids  # 100% owned, filtered
    assert 101 in player_ids
    assert 103 in player_ids  # 25% owned, within threshold


def test_rank_differentials_to_transfer_in_excludes_my_squad(db_conn):
    _seed_scenario(db_conn)
    ranked = finder.rank_differentials_to_transfer_in(
        db_conn, league_id=103056, my_manager_id=1, league_gw=10, my_squad_gw=10, start_gw=10, max_ownership_pct=30.0,
    )
    player_ids = [r["player_id"] for r in ranked]
    assert 103 not in player_ids  # already mine
    assert player_ids[0] == 101  # best differential first


def test_rank_my_differentials_only_includes_owned_players(db_conn):
    _seed_scenario(db_conn)
    ranked = finder.rank_my_differentials(
        db_conn, league_id=103056, my_manager_id=1, league_gw=10, my_squad_gw=10, start_gw=10, max_ownership_pct=30.0,
    )
    assert [r["player_id"] for r in ranked] == [103]


def test_rank_my_differentials_empty_without_squad_snapshot(db_conn):
    _seed_scenario(db_conn)
    ranked = finder.rank_my_differentials(
        db_conn, league_id=103056, my_manager_id=1, league_gw=10, my_squad_gw=None, start_gw=10, max_ownership_pct=30.0,
    )
    assert ranked == []


def test_rank_high_owned_flags_fully_owned_player(db_conn):
    _seed_scenario(db_conn)
    ranked = finder.rank_high_owned(db_conn, league_id=103056, league_gw=10, start_gw=10, min_ownership_pct=50.0)
    assert [r["player_id"] for r in ranked] == [102]
    assert ranked[0]["ownership_pct"] == 100.0
