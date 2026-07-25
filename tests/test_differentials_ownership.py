from src.differentials import ownership


def _seed_players(conn, player_ids):
    conn.execute("INSERT OR IGNORE INTO teams (id, name) VALUES (1, 'Filler United')")
    conn.executemany(
        "INSERT INTO players (id, team_id, element_type, web_name) VALUES (?, 1, 4, ?)",
        [(pid, f"P{pid}") for pid in player_ids],
    )


def _pick(conn, league_id, manager_id, gw, player_id, is_captain=False):
    conn.execute(
        "INSERT INTO league_manager_picks (league_id, manager_id, gw, player_id, is_captain) VALUES (?, ?, ?, ?, ?)",
        (league_id, manager_id, gw, player_id, int(is_captain)),
    )


def test_compute_ownership_empty_when_no_picks(db_conn):
    assert ownership.compute_ownership(db_conn, league_id=103056, gw=10) == {}


def test_compute_ownership_percentages(db_conn):
    _seed_players(db_conn, [101, 102, 103])
    # 3 managers total; player 101 owned by 2/3, player 102 by 1/3, player 103 by 0
    for manager_id in (1, 2):
        _pick(db_conn, 103056, manager_id, 10, 101)
    _pick(db_conn, 103056, 1, 10, 102)
    _pick(db_conn, 103056, 3, 10, 103)  # manager 3 only owns 103, still counts toward denominator
    db_conn.commit()

    result = ownership.compute_ownership(db_conn, 103056, 10)
    assert result[101]["owned_by"] == 2
    assert result[101]["ownership_pct"] == round(2 / 3 * 100, 1)
    assert result[102]["ownership_pct"] == round(1 / 3 * 100, 1)
    assert result[103]["ownership_pct"] == round(1 / 3 * 100, 1)


def test_compute_ownership_captaincy_percentages(db_conn):
    _seed_players(db_conn, [101])
    _pick(db_conn, 103056, 1, 10, 101, is_captain=True)
    _pick(db_conn, 103056, 2, 10, 101, is_captain=False)
    db_conn.commit()

    result = ownership.compute_ownership(db_conn, 103056, 10)
    assert result[101]["owned_by"] == 2
    assert result[101]["captained_by"] == 1
    assert result[101]["captaincy_pct"] == 50.0


def test_compute_ownership_scoped_to_league_and_gw(db_conn):
    _seed_players(db_conn, [101])
    _pick(db_conn, 103056, 1, 10, 101)
    _pick(db_conn, 999999, 1, 10, 101)  # different league -- must not count
    _pick(db_conn, 103056, 1, 11, 101)  # different gw -- must not count
    db_conn.commit()

    result = ownership.compute_ownership(db_conn, 103056, 10)
    assert result[101]["owned_by"] == 1
    assert result[101]["ownership_pct"] == 100.0
