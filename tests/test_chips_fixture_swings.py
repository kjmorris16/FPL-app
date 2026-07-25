from src.chips import fixture_swings


def _insert_teams(conn, ids):
    for tid in ids:
        conn.execute("INSERT INTO teams (id, name) VALUES (?, ?)", (tid, f"Team{tid}"))


def _insert_fixture(conn, fixture_id, event, team_h, team_a, h_diff=3, a_diff=3):
    conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES (?, ?, ?, ?, ?, ?)",
        (fixture_id, event, team_h, team_a, h_diff, a_diff),
    )


def test_get_all_team_ids(db_conn):
    _insert_teams(db_conn, [1, 2, 3])
    db_conn.commit()
    assert set(fixture_swings.get_all_team_ids(db_conn)) == {1, 2, 3}


def test_detect_double_gameweeks(db_conn):
    _insert_teams(db_conn, [1, 2, 3, 4])
    _insert_fixture(db_conn, 1, event=10, team_h=1, team_a=2)
    _insert_fixture(db_conn, 2, event=10, team_h=3, team_a=1)  # team 1 plays twice in GW10
    db_conn.commit()

    dgws = fixture_swings.detect_double_gameweeks(db_conn, 10, 10)
    assert dgws == {10: [1]}


def test_detect_double_gameweeks_none_found(db_conn):
    _insert_teams(db_conn, [1, 2])
    _insert_fixture(db_conn, 1, event=10, team_h=1, team_a=2)
    db_conn.commit()
    assert fixture_swings.detect_double_gameweeks(db_conn, 10, 10) == {}


def test_detect_blank_gameweeks(db_conn):
    _insert_teams(db_conn, [1, 2, 3])
    _insert_fixture(db_conn, 1, event=10, team_h=1, team_a=2)
    # Team 3 has no fixture in GW10
    db_conn.commit()

    bgws = fixture_swings.detect_blank_gameweeks(db_conn, 10, 10)
    assert bgws == {10: [3]}


def test_detect_blank_gameweeks_none_when_all_play(db_conn):
    _insert_teams(db_conn, [1, 2])
    _insert_fixture(db_conn, 1, event=10, team_h=1, team_a=2)
    db_conn.commit()
    assert fixture_swings.detect_blank_gameweeks(db_conn, 10, 10) == {}


def test_find_fixture_runs_good_identifies_favourable_stretch(db_conn):
    _insert_teams(db_conn, [1, 2])
    for gw in range(10, 13):
        _insert_fixture(db_conn, gw, event=gw, team_h=1, team_a=2, h_diff=2, a_diff=4)  # team 1: easy, team 2: hard
    db_conn.commit()

    good_runs = fixture_swings.find_fixture_runs(db_conn, 10, 12, window=3, good=True)
    team_ids_with_good_run = {r["team_id"] for r in good_runs}
    assert 1 in team_ids_with_good_run
    assert 2 not in team_ids_with_good_run


def test_find_fixture_runs_bad_identifies_tough_stretch(db_conn):
    _insert_teams(db_conn, [1, 2])
    for gw in range(10, 13):
        _insert_fixture(db_conn, gw, event=gw, team_h=1, team_a=2, h_diff=2, a_diff=4)
    db_conn.commit()

    bad_runs = fixture_swings.find_fixture_runs(db_conn, 10, 12, window=3, good=False)
    team_ids_with_bad_run = {r["team_id"] for r in bad_runs}
    assert 2 in team_ids_with_bad_run
    assert 1 not in team_ids_with_bad_run


def test_find_fixture_runs_respects_window_bounds(db_conn):
    _insert_teams(db_conn, [1, 2])
    _insert_fixture(db_conn, 1, event=10, team_h=1, team_a=2, h_diff=2, a_diff=4)
    db_conn.commit()

    # window=3 needs GW10-12 fully in range; end_gw=10 doesn't provide that.
    good_runs = fixture_swings.find_fixture_runs(db_conn, 10, 10, window=3, good=True)
    assert good_runs == []


def test_find_fixture_runs_sorts_best_first(db_conn):
    _insert_teams(db_conn, [1, 2, 98, 99])
    for gw in range(10, 13):
        _insert_fixture(db_conn, gw * 2, event=gw, team_h=1, team_a=99, h_diff=1, a_diff=3)
    for gw in range(10, 13):
        _insert_fixture(db_conn, gw * 2 + 1, event=gw, team_h=2, team_a=98, h_diff=2, a_diff=3)
    db_conn.commit()

    good_runs = fixture_swings.find_fixture_runs(db_conn, 10, 12, window=3, good=True)
    assert good_runs[0]["team_id"] == 1  # difficulty 1, the most favourable
    assert good_runs[0]["avg_difficulty"] <= good_runs[1]["avg_difficulty"]
