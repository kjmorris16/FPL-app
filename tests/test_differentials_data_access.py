from src.differentials import data_access


def test_get_league_managers(db_conn):
    db_conn.execute(
        "INSERT INTO league_managers (league_id, manager_id, manager_name, team_name, rank, total_points) "
        "VALUES (103056, 1213466, 'Me', 'My Team', 1, 500)"
    )
    db_conn.commit()
    managers = data_access.get_league_managers(db_conn, 103056)
    assert len(managers) == 1
    assert managers[0]["team_name"] == "My Team"


def test_get_latest_league_picks_gw_none_when_empty(db_conn):
    assert data_access.get_latest_league_picks_gw(db_conn, 103056) is None


def test_get_latest_league_picks_gw_returns_max(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Filler')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'P101')")
    db_conn.executemany(
        "INSERT INTO league_manager_picks (league_id, manager_id, gw, player_id, is_captain) VALUES (?, ?, ?, ?, 0)",
        [(103056, 1, 8, 101), (103056, 1, 10, 101)],
    )
    db_conn.commit()
    assert data_access.get_latest_league_picks_gw(db_conn, 103056) == 10


def test_get_league_picks_filters_by_league_and_gw(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Filler')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'P101')")
    db_conn.executemany(
        "INSERT INTO league_manager_picks (league_id, manager_id, gw, player_id, is_captain) VALUES (?, ?, ?, ?, 0)",
        [(103056, 1, 10, 101), (103056, 1, 11, 101), (999, 1, 10, 101)],
    )
    db_conn.commit()
    picks = data_access.get_league_picks(db_conn, 103056, 10)
    assert len(picks) == 1


def test_get_managers_with_picks(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Filler')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'P101')")
    db_conn.executemany(
        "INSERT INTO league_manager_picks (league_id, manager_id, gw, player_id, is_captain) VALUES (?, ?, ?, ?, 0)",
        [(103056, 1, 10, 101), (103056, 2, 10, 101)],
    )
    db_conn.commit()
    assert set(data_access.get_managers_with_picks(db_conn, 103056, 10)) == {1, 2}
