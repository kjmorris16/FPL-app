from src.differentials import chip_summary


def _seed_league_manager(conn, league_id, manager_id, name="Rival", team="Rival FC"):
    conn.execute(
        "INSERT INTO league_managers (league_id, manager_id, manager_name, team_name, rank, total_points) "
        "VALUES (?, ?, ?, ?, 1, 100)",
        (league_id, manager_id, name, team),
    )


def test_fetch_rival_chip_usage_refreshes_and_reports_available(db_conn, monkeypatch):
    _seed_league_manager(db_conn, 103056, 999, name="Rival Bob", team="Rival FC")
    db_conn.commit()

    def fake_get_entry_history(manager_id):
        return {"current": [], "chips": [{"name": "wildcard", "event": 5, "time": "2026-01-01T00:00:00Z"}]}

    monkeypatch.setattr(chip_summary.manager_ingest.api_client, "get_entry_history", fake_get_entry_history)

    summary = chip_summary.fetch_rival_chip_usage(db_conn, league_id=103056, current_gw=10)
    db_conn.commit()

    assert summary[999]["team_name"] == "Rival FC"
    assert summary[999]["chips_used"] == [{"chip_name": "wildcard", "event": 5}]
    assert summary[999]["available"]["wildcard"] is False  # current_gw=10 is still first-half, already used
    assert summary[999]["available"]["bboost"] is True


def test_fetch_rival_chip_usage_marks_used_chip_unavailable(db_conn, monkeypatch):
    _seed_league_manager(db_conn, 103056, 999)
    db_conn.commit()

    monkeypatch.setattr(
        chip_summary.manager_ingest.api_client, "get_entry_history",
        lambda manager_id: {"current": [], "chips": [{"name": "bboost", "event": 8, "time": "2026-01-01T00:00:00Z"}]},
    )
    summary = chip_summary.fetch_rival_chip_usage(db_conn, league_id=103056, current_gw=10)
    db_conn.commit()

    assert summary[999]["available"]["bboost"] is False


def test_fetch_rival_chip_usage_skips_refresh_when_disabled(db_conn, monkeypatch):
    _seed_league_manager(db_conn, 103056, 999)
    db_conn.execute("INSERT INTO chip_usage (manager_id, chip_name, event) VALUES (999, 'freehit', 3)")
    db_conn.commit()

    def fail_if_called(manager_id):
        raise AssertionError("should not have been called when refresh=False")

    monkeypatch.setattr(chip_summary.manager_ingest.api_client, "get_entry_history", fail_if_called)

    summary = chip_summary.fetch_rival_chip_usage(db_conn, league_id=103056, current_gw=10, refresh=False)
    assert summary[999]["chips_used"] == [{"chip_name": "freehit", "event": 3}]


def test_fetch_rival_chip_usage_multiple_managers(db_conn, monkeypatch):
    _seed_league_manager(db_conn, 103056, 1, name="A", team="TeamA")
    _seed_league_manager(db_conn, 103056, 2, name="B", team="TeamB")
    db_conn.commit()

    monkeypatch.setattr(
        chip_summary.manager_ingest.api_client, "get_entry_history",
        lambda manager_id: {"current": [], "chips": []},
    )
    summary = chip_summary.fetch_rival_chip_usage(db_conn, league_id=103056, current_gw=10)
    assert set(summary.keys()) == {1, 2}
