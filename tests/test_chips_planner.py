from src.chips import constants as c, planner


def _insert_team(conn, team_id, name=None):
    conn.execute("INSERT INTO teams (id, name, short_name) VALUES (?, ?, ?)", (team_id, name or f"Team{team_id}", f"T{team_id}"))


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


def _seed_basic_squad(conn, manager_id=1213466, gw=10):
    _insert_team(conn, 1)
    _insert_team(conn, 2)
    for pid, pos, etype in [(101, 1, 4), (102, 2, 3), (103, 12, 2)]:
        _insert_player(conn, pid, 1, element_type=etype)
        _insert_squad_pick(conn, manager_id, gw, pid, pos)
    _insert_projection(conn, 101, gw, 5.0)
    _insert_projection(conn, 102, gw, 8.0)
    _insert_projection(conn, 103, gw, 2.0)  # bench


def test_build_calendar_includes_dgw_bgw_notes(db_conn):
    _seed_basic_squad(db_conn)
    _insert_team(db_conn, 3)
    _insert_fixture(db_conn, 1, event=10, team_h=1, team_a=2)
    _insert_fixture(db_conn, 2, event=10, team_h=3, team_a=1)  # team 1 DGW
    db_conn.commit()

    calendar = planner.build_calendar(db_conn, 1213466, start_gw=10, end_gw=10, squad_gw=10)
    entry = calendar[0]
    assert entry["gw"] == 10
    assert 1 in entry["dgw_teams"]
    assert any("Double gameweek" in n for n in entry["notes"])


def test_build_calendar_computes_chip_values_when_squad_present(db_conn):
    _seed_basic_squad(db_conn)
    _insert_fixture(db_conn, 1, event=10, team_h=1, team_a=2)
    db_conn.commit()

    calendar = planner.build_calendar(db_conn, 1213466, start_gw=10, end_gw=10, squad_gw=10)
    entry = calendar[0]
    assert entry["bench_boost_value"] == 2.0
    assert entry["triple_captain_value"] == 8.0
    assert entry["triple_captain_player_id"] == 102


def test_build_calendar_without_squad_snapshot_skips_squad_specific_fields(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_fixture(db_conn, 1, event=10, team_h=1, team_a=2)
    db_conn.commit()

    calendar = planner.build_calendar(db_conn, 1213466, start_gw=10, end_gw=10, squad_gw=None)
    entry = calendar[0]
    assert "bench_boost_value" not in entry
    assert "wildcard_score" in entry  # wildcard scoring doesn't need a squad


def test_top_recommendation_returns_none_when_chip_unavailable(db_conn):
    _seed_basic_squad(db_conn)
    db_conn.commit()
    calendar = planner.build_calendar(db_conn, 1213466, start_gw=10, end_gw=10, squad_gw=10)
    result = planner.top_recommendation(calendar, c.CHIP_BENCH_BOOST, {c.CHIP_BENCH_BOOST: False})
    assert result is None


def test_top_recommendation_picks_highest_value_gameweek(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    for pid, pos in [(101, 1), (102, 12)]:
        _insert_player(db_conn, pid, 1)
        _insert_squad_pick(db_conn, 1213466, 10, pid, pos)
    _insert_projection(db_conn, 102, 10, 2.0)
    _insert_projection(db_conn, 102, 11, 6.0)  # bigger bench week at GW11
    for gw in (10, 11):
        _insert_fixture(db_conn, gw, event=gw, team_h=1, team_a=2)
    db_conn.commit()

    calendar = planner.build_calendar(db_conn, 1213466, start_gw=10, end_gw=11, squad_gw=10)
    result = planner.top_recommendation(calendar, c.CHIP_BENCH_BOOST, {c.CHIP_BENCH_BOOST: True})
    assert result["gw"] == 11


def test_top_n_gameweeks_sorted_descending(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    for pid, pos in [(101, 1), (102, 12)]:
        _insert_player(db_conn, pid, 1)
        _insert_squad_pick(db_conn, 1213466, 10, pid, pos)
    _insert_projection(db_conn, 102, 10, 1.0)
    _insert_projection(db_conn, 102, 11, 5.0)
    _insert_projection(db_conn, 102, 12, 3.0)
    for gw in (10, 11, 12):
        _insert_fixture(db_conn, gw, event=gw, team_h=1, team_a=2)
    db_conn.commit()

    calendar = planner.build_calendar(db_conn, 1213466, start_gw=10, end_gw=12, squad_gw=10)
    top = planner.top_n_gameweeks(calendar, c.CHIP_BENCH_BOOST, n=2)
    assert [e["gw"] for e in top] == [11, 12]


def test_describe_recommendation_bench_boost():
    entry = {"gw": 20, "bench_boost_value": 12.5, "notes": ["Double gameweek: ARS, CHE"]}
    text = planner.describe_recommendation(c.CHIP_BENCH_BOOST, entry)
    assert "GW20" in text
    assert "12.5" in text
    assert "Double gameweek" in text


def test_describe_recommendation_triple_captain_uses_player_name():
    entry = {"gw": 20, "triple_captain_value": 7.0, "triple_captain_player_id": 999, "notes": []}
    text = planner.describe_recommendation(c.CHIP_TRIPLE_CAPTAIN, entry, players_by_id={999: {"web_name": "Salah"}})
    assert "Salah" in text
    assert "7.0" in text


def test_describe_recommendation_wildcard_mentions_team_names():
    entry = {"gw": 15, "wildcard_good_run_teams": [1], "wildcard_dgw_teams": [2], "notes": []}
    text = planner.describe_recommendation(c.CHIP_WILDCARD, entry, teams={1: "ARS", 2: "CHE"})
    assert "ARS" in text
    assert "CHE" in text


def test_describe_recommendation_free_hit():
    entry = {"gw": 18, "free_hit_score": 4, "notes": ["Blank gameweek: ARS, CHE"]}
    text = planner.describe_recommendation(c.CHIP_FREE_HIT, entry)
    assert "GW18" in text
    assert "4" in text
