from src.ingest import manager


def test_compute_sell_price_no_profit_sells_at_current_price():
    assert manager.compute_sell_price(purchase_price=50, current_price=50) == 50


def test_compute_sell_price_loss_eats_full_loss():
    assert manager.compute_sell_price(purchase_price=60, current_price=55) == 55


def test_compute_sell_price_profit_keeps_half_rounded_down():
    # profit = 10 (1.0m), half = 5 (0.5m) -> sell at purchase + 5
    assert manager.compute_sell_price(purchase_price=50, current_price=60) == 55


def test_compute_sell_price_profit_rounds_down_odd_profit():
    # profit = 3 (0.3m), half = 1 (floor(1.5)) -> sell at purchase + 1
    assert manager.compute_sell_price(purchase_price=50, current_price=53) == 51


def test_reconstruct_purchase_prices_uses_most_recent_transfer_in():
    transfers = [
        {"element_in": 101, "element_in_cost": 50, "event": 3, "time": "2026-01-01T00:00:00Z"},
        {"element_in": 101, "element_in_cost": 65, "event": 9, "time": "2026-02-01T00:00:00Z"},
        {"element_in": 102, "element_in_cost": 45, "event": 5, "time": "2026-01-15T00:00:00Z"},
    ]
    prices = manager.reconstruct_purchase_prices(transfers)
    assert prices[101] == 65  # the later (GW9) purchase, not the GW3 one
    assert prices[102] == 45


def _history_row(event, transfers=0, cost=0):
    return {"event": event, "event_transfers": transfers, "event_transfers_cost": cost}


def test_compute_free_transfers_starts_at_one_for_gw2():
    assert manager.compute_free_transfers([], [], upcoming_gw=2) == 1


def test_compute_free_transfers_banks_unused_transfer():
    history = [_history_row(2, transfers=0, cost=0)]
    # Didn't use GW2's free transfer -> 2 available entering GW3
    assert manager.compute_free_transfers(history, [], upcoming_gw=3) == 2


def test_compute_free_transfers_using_the_free_transfer_keeps_it_at_one():
    history = [_history_row(2, transfers=1, cost=0)]
    assert manager.compute_free_transfers(history, [], upcoming_gw=3) == 1


def test_compute_free_transfers_caps_at_five():
    history = [_history_row(gw, transfers=0, cost=0) for gw in range(2, 10)]
    assert manager.compute_free_transfers(history, [], upcoming_gw=10) == 5


def test_compute_free_transfers_hit_reduces_next_gw_availability():
    # Entering GW2 with 1 FT, took a -4 hit (2 transfers, cost -4 => 1 hit taken,
    # 1 free transfer used) -> 1 - 1 + 1 = 1 available entering GW3
    history = [_history_row(2, transfers=2, cost=-4)]
    assert manager.compute_free_transfers(history, [], upcoming_gw=3) == 1


def test_compute_free_transfers_double_hit_does_not_go_negative():
    # 1 FT available, took 3 transfers costing -8 (2 hits) -> free_used capped at 1
    history = [_history_row(2, transfers=3, cost=-8)]
    assert manager.compute_free_transfers(history, [], upcoming_gw=3) == 1


def test_compute_free_transfers_wildcard_gameweek_does_not_deplete_counter():
    history = [_history_row(2, transfers=8, cost=0)]  # 8 transfers, no cost: a chip week
    chips = [{"name": "wildcard", "event": 2}]
    # Chip week is skipped entirely -> just +1 rollover as normal
    assert manager.compute_free_transfers(history, chips, upcoming_gw=3) == 2


def test_fetch_picks_with_fallback_falls_back_on_404(monkeypatch):
    calls = []

    def fake_get_entry_picks(manager_id, gw):
        calls.append(gw)
        if gw == 11:
            raise RuntimeError("404")
        return {"picks": [], "entry_history": {}}

    monkeypatch.setattr(manager.api_client, "get_entry_picks", fake_get_entry_picks)

    gw, payload = manager.fetch_picks_with_fallback(1213466, 11)
    assert gw == 10
    assert calls == [11, 10]


def test_fetch_squad_snapshot_stores_snapshot_and_returns_dict(db_conn, monkeypatch):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost) VALUES (101, 1, 4, 'Sharpe', 90)")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost) VALUES (102, 1, 2, 'Backman', 50)")
    db_conn.execute("INSERT INTO events (id, name, is_current) VALUES (10, 'GW10', 1)")
    db_conn.commit()

    def fake_get_entry_picks(manager_id, gw):
        assert manager_id == 1213466
        return {
            "entry_history": {"bank": 15, "value": 1005},
            "picks": [
                {"element": 101, "position": 1, "multiplier": 2, "is_captain": True, "is_vice_captain": False},
                {"element": 102, "position": 2, "multiplier": 1, "is_captain": False, "is_vice_captain": True},
            ],
        }

    def fake_get_entry_history(manager_id):
        return {"current": [], "chips": []}

    def fake_get_entry_transfers(manager_id):
        return [{"element_in": 101, "element_in_cost": 80, "event": 3, "time": "2026-01-01T00:00:00Z"}]

    monkeypatch.setattr(manager.api_client, "get_entry_picks", fake_get_entry_picks)
    monkeypatch.setattr(manager.api_client, "get_entry_history", fake_get_entry_history)
    monkeypatch.setattr(manager.api_client, "get_entry_transfers", fake_get_entry_transfers)

    snapshot = manager.fetch_squad_snapshot(db_conn, manager_id=1213466, gw=10)
    db_conn.commit()

    assert snapshot["bank"] == 15
    assert snapshot["free_transfers"] == 1
    assert len(snapshot["squad"]) == 2

    sharpe = next(s for s in snapshot["squad"] if s["player_id"] == 101)
    assert sharpe["purchase_price"] == 80
    assert sharpe["sell_price"] == manager.compute_sell_price(80, 90)
    assert sharpe["is_captain"] is True

    backman = next(s for s in snapshot["squad"] if s["player_id"] == 102)
    assert backman["purchase_price"] == 50  # never transferred in -> fallback to current price
    assert backman["sell_price"] == 50

    stored_manager_row = db_conn.execute(
        "SELECT * FROM my_manager_snapshot WHERE manager_id = 1213466 AND gw = 10"
    ).fetchone()
    assert stored_manager_row["bank"] == 15

    stored_squad_rows = db_conn.execute(
        "SELECT * FROM my_squad_history WHERE manager_id = 1213466 AND gw = 10"
    ).fetchall()
    assert len(stored_squad_rows) == 2


def test_fetch_chip_usage_stores_rows(db_conn, monkeypatch):
    def fake_get_entry_history(manager_id):
        return {"current": [], "chips": [{"name": "wildcard", "event": 7, "time": "2026-01-01T00:00:00Z"}]}

    monkeypatch.setattr(manager.api_client, "get_entry_history", fake_get_entry_history)

    chips = manager.fetch_chip_usage(db_conn, manager_id=1213466)
    db_conn.commit()

    assert chips == [{"name": "wildcard", "event": 7, "time": "2026-01-01T00:00:00Z"}]
    rows = db_conn.execute("SELECT * FROM chip_usage WHERE manager_id = 1213466").fetchall()
    assert len(rows) == 1
    assert rows[0]["chip_name"] == "wildcard"
    assert rows[0]["event"] == 7


def test_fetch_chip_usage_supports_two_wildcards(db_conn, monkeypatch):
    def fake_get_entry_history(manager_id):
        return {
            "current": [],
            "chips": [
                {"name": "wildcard", "event": 7, "time": "2026-01-01T00:00:00Z"},
                {"name": "wildcard", "event": 25, "time": "2026-03-01T00:00:00Z"},
            ],
        }

    monkeypatch.setattr(manager.api_client, "get_entry_history", fake_get_entry_history)
    manager.fetch_chip_usage(db_conn, manager_id=1213466)
    db_conn.commit()

    rows = db_conn.execute(
        "SELECT event FROM chip_usage WHERE manager_id = 1213466 AND chip_name = 'wildcard' ORDER BY event"
    ).fetchall()
    assert [r["event"] for r in rows] == [7, 25]


def test_fetch_chip_usage_no_chips_stores_nothing(db_conn, monkeypatch):
    monkeypatch.setattr(manager.api_client, "get_entry_history", lambda manager_id: {"current": [], "chips": []})
    manager.fetch_chip_usage(db_conn, manager_id=1213466)
    db_conn.commit()
    assert db_conn.execute("SELECT * FROM chip_usage").fetchall() == []


def test_fetch_squad_snapshot_also_stores_chip_usage(db_conn, monkeypatch):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost) VALUES (101, 1, 4, 'Sharpe', 90)")
    db_conn.commit()

    monkeypatch.setattr(
        manager.api_client, "get_entry_picks",
        lambda manager_id, gw: {"entry_history": {"bank": 0, "value": 1000}, "picks": []},
    )
    monkeypatch.setattr(
        manager.api_client, "get_entry_history",
        lambda manager_id: {"current": [], "chips": [{"name": "bboost", "event": 9, "time": "2026-01-01T00:00:00Z"}]},
    )
    monkeypatch.setattr(manager.api_client, "get_entry_transfers", lambda manager_id: [])

    manager.fetch_squad_snapshot(db_conn, manager_id=1213466, gw=10)
    db_conn.commit()

    rows = db_conn.execute("SELECT * FROM chip_usage WHERE manager_id = 1213466").fetchall()
    assert len(rows) == 1
    assert rows[0]["chip_name"] == "bboost"


def test_fetch_squad_snapshot_is_idempotent_upsert(db_conn, monkeypatch):
    db_conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United')")
    db_conn.execute("INSERT INTO players (id, team_id, element_type, web_name, now_cost) VALUES (101, 1, 4, 'Sharpe', 90)")
    db_conn.commit()

    def fake_get_entry_picks(manager_id, gw):
        return {
            "entry_history": {"bank": 10, "value": 1000},
            "picks": [{"element": 101, "position": 1, "multiplier": 1, "is_captain": False, "is_vice_captain": False}],
        }

    monkeypatch.setattr(manager.api_client, "get_entry_picks", fake_get_entry_picks)
    monkeypatch.setattr(manager.api_client, "get_entry_history", lambda manager_id: {"current": [], "chips": []})
    monkeypatch.setattr(manager.api_client, "get_entry_transfers", lambda manager_id: [])

    manager.fetch_squad_snapshot(db_conn, manager_id=1213466, gw=10)
    manager.fetch_squad_snapshot(db_conn, manager_id=1213466, gw=10)
    db_conn.commit()

    rows = db_conn.execute("SELECT * FROM my_squad_history WHERE manager_id = 1213466 AND gw = 10").fetchall()
    assert len(rows) == 1


def _insert_squad_of_players(conn, player_ids, team_id=1, element_type=3, cost=50):
    conn.execute("INSERT OR IGNORE INTO teams (id, name) VALUES (?, ?)", (team_id, "Home United"))
    for player_id in player_ids:
        conn.execute(
            "INSERT INTO players (id, team_id, element_type, web_name, now_cost) VALUES (?, ?, ?, ?, ?)",
            (player_id, team_id, element_type, f"Player{player_id}", cost),
        )
    conn.commit()


def test_save_manual_squad_stores_all_players_in_given_order(db_conn):
    player_ids = list(range(101, 116))
    _insert_squad_of_players(db_conn, player_ids)

    manager.save_manual_squad(db_conn, manager_id=1213466, gw=1, player_ids=player_ids, captain_id=101, vice_captain_id=102)
    db_conn.commit()

    rows = db_conn.execute(
        "SELECT player_id, squad_position FROM my_squad_history WHERE manager_id = 1213466 AND gw = 1 ORDER BY squad_position"
    ).fetchall()
    assert [r["player_id"] for r in rows] == player_ids
    assert [r["squad_position"] for r in rows] == list(range(1, 16))


def test_save_manual_squad_sets_captain_multiplier_to_two(db_conn):
    player_ids = list(range(101, 116))
    _insert_squad_of_players(db_conn, player_ids)

    manager.save_manual_squad(db_conn, manager_id=1213466, gw=1, player_ids=player_ids, captain_id=101, vice_captain_id=102)
    db_conn.commit()

    captain_row = db_conn.execute(
        "SELECT is_captain, is_vice_captain, multiplier FROM my_squad_history WHERE manager_id = 1213466 AND gw = 1 AND player_id = 101"
    ).fetchone()
    assert captain_row["is_captain"] == 1
    assert captain_row["is_vice_captain"] == 0
    assert captain_row["multiplier"] == 2

    vice_row = db_conn.execute(
        "SELECT is_captain, is_vice_captain, multiplier FROM my_squad_history WHERE manager_id = 1213466 AND gw = 1 AND player_id = 102"
    ).fetchone()
    assert vice_row["is_captain"] == 0
    assert vice_row["is_vice_captain"] == 1
    assert vice_row["multiplier"] == 1


def test_save_manual_squad_computes_squad_value_from_current_prices(db_conn):
    player_ids = list(range(101, 116))
    _insert_squad_of_players(db_conn, player_ids, cost=50)  # 15 * 50 = 750

    manager.save_manual_squad(db_conn, manager_id=1213466, gw=1, player_ids=player_ids, captain_id=101, vice_captain_id=102)
    db_conn.commit()

    snapshot_row = db_conn.execute(
        "SELECT squad_value FROM my_manager_snapshot WHERE manager_id = 1213466 AND gw = 1"
    ).fetchone()
    assert snapshot_row["squad_value"] == 750


def test_save_manual_squad_replaces_a_prior_manual_squad_entirely(db_conn):
    first_ids = list(range(101, 116))
    second_ids = list(range(201, 216))
    _insert_squad_of_players(db_conn, first_ids)
    _insert_squad_of_players(db_conn, second_ids)

    manager.save_manual_squad(db_conn, manager_id=1213466, gw=1, player_ids=first_ids, captain_id=101, vice_captain_id=102)
    manager.save_manual_squad(db_conn, manager_id=1213466, gw=1, player_ids=second_ids, captain_id=201, vice_captain_id=202)
    db_conn.commit()

    rows = db_conn.execute("SELECT player_id FROM my_squad_history WHERE manager_id = 1213466 AND gw = 1").fetchall()
    stored_ids = {r["player_id"] for r in rows}
    assert stored_ids == set(second_ids)
