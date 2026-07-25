from src.preseason import data_access


def test_get_previous_season_stats_empty(db_conn):
    assert data_access.get_previous_season_stats(db_conn) == {}


def test_get_previous_season_stats(db_conn):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Filler')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name) VALUES (101, 1, 4, 'Striker')")
    db_conn.execute(
        "INSERT INTO player_previous_season_stats (player_id, season_name, minutes, total_points) VALUES (101, '2024/25', 2000, 150)"
    )
    db_conn.commit()
    stats = data_access.get_previous_season_stats(db_conn)
    assert stats[101]["minutes"] == 2000


def test_get_friendly_appearances_summary_returns_empty_when_table_missing(db_conn):
    # friendly_appearances is only created by the (not yet built) friendlies
    # ingestion module -- this must degrade gracefully, not error.
    assert data_access.get_friendly_appearances_summary(db_conn) == {}


def test_get_friendly_appearances_summary_aggregates_when_table_exists(db_conn):
    db_conn.execute(
        "CREATE TABLE friendly_appearances (player_id INTEGER, minutes INTEGER, goals INTEGER, assists INTEGER)"
    )
    db_conn.executemany(
        "INSERT INTO friendly_appearances (player_id, minutes, goals, assists) VALUES (?, ?, ?, ?)",
        [(101, 45, 1, 0), (101, 60, 0, 1)],
    )
    db_conn.commit()

    summary = data_access.get_friendly_appearances_summary(db_conn)
    assert summary[101]["minutes"] == 105
    assert summary[101]["goals"] == 1
    assert summary[101]["assists"] == 1
    assert summary[101]["appearances"] == 2


def test_get_preseason_creator_notes_returns_empty_when_table_missing(db_conn):
    assert data_access.get_preseason_creator_notes(db_conn, target_gw=1) == {}


def test_get_preseason_creator_notes_when_table_exists(db_conn):
    db_conn.execute(
        "CREATE TABLE creator_insights (player_id INTEGER, gameweek INTEGER, sentiment TEXT, reasoning TEXT, creator TEXT)"
    )
    db_conn.execute(
        "INSERT INTO creator_insights (player_id, gameweek, sentiment, reasoning, creator) VALUES (101, 1, 'buy', 'Great fixtures', 'FPL Raptor')"
    )
    db_conn.commit()

    notes = data_access.get_preseason_creator_notes(db_conn, target_gw=1)
    assert notes[101][0]["sentiment"] == "buy"
    assert notes[101][0]["creator"] == "FPL Raptor"
