from src.scoring import constants as c, data_access, projections


def _insert_team(conn, team_id, name, attack_home=1200, attack_away=1200, defence_home=1200, defence_away=1200):
    conn.execute(
        "INSERT INTO teams (id, name, strength_attack_home, strength_attack_away, "
        "strength_defence_home, strength_defence_away) VALUES (?, ?, ?, ?, ?, ?)",
        (team_id, name, attack_home, attack_away, defence_home, defence_away),
    )


def _insert_player(conn, player_id, team_id, element_type, web_name, status="a", chance=None):
    conn.execute(
        "INSERT INTO players (id, team_id, element_type, web_name, status, "
        "chance_of_playing_next_round) VALUES (?, ?, ?, ?, ?, ?)",
        (player_id, team_id, element_type, web_name, status, chance),
    )


def _insert_fixture(conn, fixture_id, event, team_h, team_a, h_diff=3, a_diff=3):
    conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (fixture_id, event, team_h, team_a, h_diff, a_diff),
    )


def _insert_gw_stat(conn, player_id, gw, minutes=90, expected_goals=0.3, expected_assists=0.1, bonus=1):
    conn.execute(
        "INSERT INTO gameweek_stats (player_id, gw, minutes, expected_goals, expected_assists, bonus) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (player_id, gw, minutes, expected_goals, expected_assists, bonus),
    )


def _setup_common(conn):
    _insert_team(conn, 1, "Home United")
    _insert_team(conn, 2, "Away FC")
    _insert_team(conn, 3, "Third Town")
    conn.commit()


def test_established_striker_gets_nonzero_projection(db_conn):
    _setup_common(db_conn)
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Striker")
    for gw in range(1, 7):
        _insert_gw_stat(db_conn, 101, gw, minutes=90, expected_goals=0.5, expected_assists=0.1)
    _insert_fixture(db_conn, 1001, event=10, team_h=1, team_a=2)
    db_conn.commit()

    rows = projections.compute_projections(db_conn, start_gw=10, horizon_gws=1)
    row = next(r for r in rows if r[0] == 101)
    _, gw, projected_points, confidence, _ = row
    assert gw == 10
    assert projected_points > 0
    assert confidence == 1.0  # 6 GWs * 90 mins == FULL_CONFIDENCE_MINUTES


def test_double_gameweek_sums_across_both_fixtures(db_conn):
    _setup_common(db_conn)
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Striker")
    for gw in range(1, 7):
        _insert_gw_stat(db_conn, 101, gw, minutes=90, expected_goals=0.5, expected_assists=0.1)
    _insert_fixture(db_conn, 1001, event=10, team_h=1, team_a=2)
    _insert_fixture(db_conn, 1002, event=10, team_h=3, team_a=1)  # second fixture, same GW
    db_conn.commit()

    dgw_rows = projections.compute_projections(db_conn, start_gw=10, horizon_gws=1)
    dgw_points = next(r[2] for r in dgw_rows if r[0] == 101)

    _insert_fixture(db_conn, 1003, event=12, team_h=1, team_a=2)
    single_rows = projections.compute_projections(db_conn, start_gw=12, horizon_gws=1)
    single_points = next(r[2] for r in single_rows if r[0] == 101)

    assert dgw_points > single_points
    assert round(dgw_points, 1) == round(single_points * 2, 1)


def test_blank_gameweek_projects_zero_with_full_confidence(db_conn):
    _setup_common(db_conn)
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Striker")
    for gw in range(1, 7):
        _insert_gw_stat(db_conn, 101, gw, minutes=90, expected_goals=0.5, expected_assists=0.1)
    # No fixture at all for team 1 in GW15
    db_conn.commit()

    rows = projections.compute_projections(db_conn, start_gw=15, horizon_gws=1)
    row = next(r for r in rows if r[0] == 101)
    assert row[2] == 0.0
    assert row[3] == 1.0


def test_new_signing_falls_back_to_position_average(db_conn):
    _setup_common(db_conn)
    # Established forwards to establish a position average.
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Established1")
    _insert_player(db_conn, 102, team_id=1, element_type=c.FWD, web_name="Established2")
    for pid in (101, 102):
        for gw in range(1, 7):
            _insert_gw_stat(db_conn, pid, gw, minutes=90, expected_goals=0.4, expected_assists=0.1)
    # Brand new signing, no gameweek_stats history at all.
    _insert_player(db_conn, 103, team_id=1, element_type=c.FWD, web_name="NewSigning")
    _insert_fixture(db_conn, 1001, event=10, team_h=1, team_a=2)
    db_conn.commit()

    rows = projections.compute_projections(db_conn, start_gw=10, horizon_gws=1)
    new_signing_row = next(r for r in rows if r[0] == 103)
    established_row = next(r for r in rows if r[0] == 101)

    assert new_signing_row[2] > 0  # gets a non-zero projection from the position average
    assert new_signing_row[3] == c.FALLBACK_CONFIDENCE_NO_HISTORY
    assert established_row[3] == 1.0


def test_injured_player_projection_reduced_by_availability(db_conn):
    _setup_common(db_conn)
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Fit", status="a")
    _insert_player(db_conn, 102, team_id=1, element_type=c.FWD, web_name="Injured", status="i")
    for pid in (101, 102):
        for gw in range(1, 7):
            _insert_gw_stat(db_conn, pid, gw, minutes=90, expected_goals=0.5, expected_assists=0.1)
    _insert_fixture(db_conn, 1001, event=10, team_h=1, team_a=2)
    db_conn.commit()

    rows = projections.compute_projections(db_conn, start_gw=10, horizon_gws=1)
    fit_points = next(r[2] for r in rows if r[0] == 101)
    injured_points = next(r[2] for r in rows if r[0] == 102)

    assert injured_points < fit_points


def test_run_writes_projections_to_db(db_conn, monkeypatch):
    _setup_common(db_conn)
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Striker")
    for gw in range(1, 7):
        _insert_gw_stat(db_conn, 101, gw, minutes=90, expected_goals=0.5, expected_assists=0.1)
    _insert_fixture(db_conn, 1001, event=10, team_h=1, team_a=2)
    db_conn.commit()

    rows = projections.compute_projections(db_conn, start_gw=10, horizon_gws=3)
    data_access.upsert_projections(db_conn, rows)
    db_conn.commit()

    stored = db_conn.execute(
        "SELECT * FROM player_projections WHERE player_id = 101 ORDER BY gameweek"
    ).fetchall()
    assert [r["gameweek"] for r in stored] == [10, 11, 12]


def test_get_horizon_projection_sums_across_gameweeks(db_conn):
    _setup_common(db_conn)
    _insert_player(db_conn, 101, team_id=1, element_type=c.FWD, web_name="Striker")
    now = "2026-01-01T00:00:00Z"
    db_conn.executemany(
        "INSERT INTO player_projections (player_id, gameweek, projected_points, confidence, computed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [(101, 10, 5.0, 0.8, now), (101, 11, 3.0, 0.6, now), (101, 12, 4.0, 1.0, now)],
    )
    db_conn.commit()

    total, avg_conf = data_access.get_horizon_projection(db_conn, 101, start_gw=10, num_gws=3)
    assert total == 12.0
    assert round(avg_conf, 3) == round((0.8 + 0.6 + 1.0) / 3, 3)
