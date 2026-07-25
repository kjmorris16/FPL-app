import pytest

from src.differentials import ingestion


def test_fetch_league_managers_stores_single_page(db_conn, monkeypatch):
    def fake_get_league_standings(league_id, page=1):
        assert league_id == 103056
        assert page == 1
        return {
            "standings": {
                "has_next": False,
                "results": [
                    {"entry": 1213466, "player_name": "Me", "entry_name": "My Team", "rank": 1, "total": 500},
                    {"entry": 999, "player_name": "Rival", "entry_name": "Rival Team", "rank": 2, "total": 480},
                ],
            }
        }

    monkeypatch.setattr(ingestion.api_client, "get_league_standings", fake_get_league_standings)

    managers = ingestion.fetch_league_managers(db_conn, league_id=103056)
    db_conn.commit()

    assert len(managers) == 2
    rows = db_conn.execute("SELECT * FROM league_managers WHERE league_id = 103056 ORDER BY rank").fetchall()
    assert len(rows) == 2
    assert rows[0]["manager_id"] == 1213466
    assert rows[0]["team_name"] == "My Team"
    assert rows[1]["manager_id"] == 999


def test_fetch_league_managers_paginates(db_conn, monkeypatch):
    pages = {
        1: {"standings": {"has_next": True, "results": [{"entry": 1, "player_name": "A", "entry_name": "TeamA", "rank": 1, "total": 100}]}},
        2: {"standings": {"has_next": False, "results": [{"entry": 2, "player_name": "B", "entry_name": "TeamB", "rank": 2, "total": 90}]}},
    }

    def fake_get_league_standings(league_id, page=1):
        return pages[page]

    monkeypatch.setattr(ingestion.api_client, "get_league_standings", fake_get_league_standings)

    managers = ingestion.fetch_league_managers(db_conn, league_id=103056)
    db_conn.commit()

    assert len(managers) == 2
    rows = db_conn.execute("SELECT manager_id FROM league_managers WHERE league_id = 103056").fetchall()
    assert {r["manager_id"] for r in rows} == {1, 2}


def test_fetch_league_managers_raises_helpful_error_for_missing_league(db_conn, monkeypatch):
    def fake_get_league_standings(league_id, page=1):
        raise RuntimeError("404")

    monkeypatch.setattr(ingestion.api_client, "get_league_standings", fake_get_league_standings)

    with pytest.raises(RuntimeError, match="DEFAULT_LEAGUE_ID"):
        ingestion.fetch_league_managers(db_conn, league_id=103056)


def test_fetch_league_managers_upsert_updates_existing_row(db_conn, monkeypatch):
    def fake_page(rank):
        return {
            "standings": {
                "has_next": False,
                "results": [{"entry": 1213466, "player_name": "Me", "entry_name": "My Team", "rank": rank, "total": 500}],
            }
        }

    monkeypatch.setattr(ingestion.api_client, "get_league_standings", lambda league_id, page=1: fake_page(3))
    ingestion.fetch_league_managers(db_conn, league_id=103056)
    monkeypatch.setattr(ingestion.api_client, "get_league_standings", lambda league_id, page=1: fake_page(1))
    ingestion.fetch_league_managers(db_conn, league_id=103056)
    db_conn.commit()

    rows = db_conn.execute("SELECT * FROM league_managers WHERE league_id = 103056").fetchall()
    assert len(rows) == 1
    assert rows[0]["rank"] == 1


def _seed_league_managers(conn, league_id, manager_ids):
    conn.executemany(
        "INSERT INTO league_managers (league_id, manager_id, manager_name, team_name, rank, total_points, pulled_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(league_id, mid, f"Manager{mid}", f"Team{mid}", i + 1, 100, "2026-01-01T00:00:00Z") for i, mid in enumerate(manager_ids)],
    )


def _seed_players(conn, player_ids):
    conn.execute("INSERT OR IGNORE INTO teams (id, name) VALUES (1, 'Filler United')")
    conn.executemany(
        "INSERT INTO players (id, team_id, element_type, web_name) VALUES (?, 1, 4, ?)",
        [(pid, f"P{pid}") for pid in player_ids],
    )


def test_fetch_league_picks_stores_rows_for_each_manager(db_conn, monkeypatch):
    _seed_league_managers(db_conn, 103056, [1213466, 999])
    _seed_players(db_conn, [101, 102])
    db_conn.execute("INSERT INTO events (id, name, is_current) VALUES (10, 'GW10', 1)")
    db_conn.commit()

    def fake_fetch_picks(manager_id, gw):
        return gw, {
            "picks": [
                {"element": 101, "is_captain": manager_id == 1213466},
                {"element": 102, "is_captain": False},
            ]
        }

    monkeypatch.setattr(ingestion.manager_ingest, "fetch_picks_with_fallback", fake_fetch_picks)

    count = ingestion.fetch_league_picks(db_conn, league_id=103056, gw=10)
    db_conn.commit()

    assert count == 2
    rows = db_conn.execute("SELECT * FROM league_manager_picks WHERE league_id = 103056 AND gw = 10").fetchall()
    assert len(rows) == 4
    my_captain_row = db_conn.execute(
        "SELECT * FROM league_manager_picks WHERE league_id = 103056 AND manager_id = 1213466 AND player_id = 101"
    ).fetchone()
    assert my_captain_row["is_captain"] == 1


def test_fetch_league_picks_skips_manager_on_error(db_conn, monkeypatch):
    _seed_league_managers(db_conn, 103056, [1213466, 999])
    _seed_players(db_conn, [101])
    db_conn.commit()

    def fake_fetch_picks(manager_id, gw):
        if manager_id == 999:
            raise RuntimeError("404")
        return gw, {"picks": [{"element": 101, "is_captain": False}]}

    monkeypatch.setattr(ingestion.manager_ingest, "fetch_picks_with_fallback", fake_fetch_picks)

    count = ingestion.fetch_league_picks(db_conn, league_id=103056, gw=10)
    db_conn.commit()

    assert count == 1
    rows = db_conn.execute("SELECT DISTINCT manager_id FROM league_manager_picks WHERE league_id = 103056").fetchall()
    assert {r["manager_id"] for r in rows} == {1213466}


def test_fetch_league_picks_fetches_managers_when_none_stored(db_conn, monkeypatch):
    _seed_players(db_conn, [101])
    db_conn.commit()

    def fake_get_league_standings(league_id, page=1):
        return {"standings": {"has_next": False, "results": [{"entry": 1213466, "player_name": "Me", "entry_name": "My Team", "rank": 1, "total": 500}]}}

    monkeypatch.setattr(ingestion.api_client, "get_league_standings", fake_get_league_standings)
    monkeypatch.setattr(
        ingestion.manager_ingest, "fetch_picks_with_fallback",
        lambda manager_id, gw: (gw, {"picks": [{"element": 101, "is_captain": True}]}),
    )

    count = ingestion.fetch_league_picks(db_conn, league_id=103056, gw=10)
    db_conn.commit()

    assert count == 1
    assert db_conn.execute("SELECT * FROM league_managers WHERE league_id = 103056").fetchall()
