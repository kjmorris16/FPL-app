from src.transfers import constants as c, weakness


def _hist_row(gw, mins=90, xg=0.0, xa=0.0):
    return {"gw": gw, "minutes": mins, "expected_goals": xg, "expected_assists": xa}


def _player(player_id, element_type=c.FWD, team_id=1, now_cost=70, sell_price=70, status="a", chance=None):
    return {
        "player_id": player_id,
        "element_type": element_type,
        "team_id": team_id,
        "web_name": f"P{player_id}",
        "now_cost": now_cost,
        "sell_price": sell_price,
        "status": status,
        "chance_of_playing_next_round": chance,
    }


# --- compute_replacement_gap ---

def test_compute_replacement_gap_no_candidates_is_zero():
    assert weakness.compute_replacement_gap(5.0, []) == 0.0


def test_compute_replacement_gap_best_available_minus_own():
    assert weakness.compute_replacement_gap(5.0, [4.0, 8.0, 6.0]) == 3.0


def test_compute_replacement_gap_negative_when_player_already_best():
    assert weakness.compute_replacement_gap(10.0, [4.0, 6.0]) == -4.0


# --- compute_form_decline ---

def test_compute_form_decline_no_history_is_zero():
    assert weakness.compute_form_decline([]) == 0.0


def test_compute_form_decline_detects_a_drop_in_recent_output():
    # Season: strong all year. Recent 6: gone quiet.
    season = [_hist_row(gw, xg=0.6, xa=0.2) for gw in range(1, 7)]
    recent_quiet = [_hist_row(gw, xg=0.0, xa=0.0) for gw in range(7, 13)]
    history = season + recent_quiet
    decline = weakness.compute_form_decline(history, window=6)
    assert decline > 0


def test_compute_form_decline_clamped_to_zero_when_form_improving():
    season = [_hist_row(gw, xg=0.1, xa=0.0) for gw in range(1, 7)]
    recent_hot = [_hist_row(gw, xg=0.8, xa=0.3) for gw in range(7, 13)]
    history = season + recent_hot
    assert weakness.compute_form_decline(history, window=6) == 0.0


# --- compute_fixture_swing ---

def test_compute_fixture_swing_positive_when_future_tougher():
    assert weakness.compute_fixture_swing(future_avg_difficulty=4.5, season_avg_difficulty=2.5) == 2.0


def test_compute_fixture_swing_clamped_to_zero_when_future_easier():
    assert weakness.compute_fixture_swing(future_avg_difficulty=2.0, season_avg_difficulty=4.0) == 0.0


def test_compute_fixture_swing_zero_when_missing_data():
    assert weakness.compute_fixture_swing(None, 3.0) == 0.0
    assert weakness.compute_fixture_swing(3.0, None) == 0.0


# --- compute_minutes_risk ---

def test_compute_minutes_risk_flags_unavailable_status():
    player = _player(1, status="i", chance=None)
    risk = weakness.compute_minutes_risk(player, [], [])
    assert risk == 1.0  # fully unavailable -> max availability risk, no history to add more


def test_compute_minutes_risk_flags_declining_recent_starts():
    player = _player(1)
    # Started every game all season, but benched the last 6.
    history = [_hist_row(gw, mins=90) for gw in range(1, 13)] + [_hist_row(gw, mins=0) for gw in range(13, 19)]
    risk = weakness.compute_minutes_risk(player, history, [])
    assert risk > 0


def test_compute_minutes_risk_flags_teammate_overtaking():
    player = _player(1)
    # This player's recent starts have dropped off...
    history = [_hist_row(gw, mins=45) for gw in range(1, 7)]
    # ...while a same-position teammate has been starting every game recently.
    teammate_history = [_hist_row(gw, mins=90) for gw in range(1, 7)]
    risk_with_teammate = weakness.compute_minutes_risk(player, history, [teammate_history])
    risk_without_teammate = weakness.compute_minutes_risk(player, history, [])
    assert risk_with_teammate > risk_without_teammate


def test_compute_minutes_risk_small_teammate_gap_is_not_flagged():
    player = _player(1)
    history = [_hist_row(gw, mins=90) for gw in range(1, 7)]  # started every recent game, ratio 1.0
    teammate_history = [_hist_row(gw, mins=90) for gw in range(1, 7)]  # same ratio, no real gap
    risk = weakness.compute_minutes_risk(player, history, [teammate_history])
    assert risk == 0.0


# --- compute_weakness_score ---

def test_compute_weakness_score_matches_the_weighted_formula():
    score = weakness.compute_weakness_score(replacement_gap=4.0, form_decline=2.0, fixture_swing=1.0, minutes_risk=0.5)
    expected = round(0.5 * 4.0 + 0.25 * 2.0 + 0.15 * 1.0 + 0.1 * 0.5, 3)
    assert score == expected


# --- rank_squad_weakness (integration, needs conn for fixture-difficulty lookups) ---

def _seed_teams_and_fixtures(conn):
    conn.execute("INSERT INTO teams (id, name) VALUES (1, 'Home United'), (2, 'Away FC'), (3, 'Third Town')")
    # Team 1's season-so-far fixtures (GW1-5): easy (difficulty 2).
    for gw in range(1, 6):
        conn.execute(
            "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES (?, ?, 1, 2, 2, 2)",
            (gw, gw),
        )
    # Team 1's upcoming fixtures (GW6-10): much tougher (difficulty 5).
    for gw in range(6, 11):
        conn.execute(
            "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES (?, ?, 1, 2, 5, 5)",
            (gw + 100, gw),
        )
    conn.commit()


def test_rank_squad_weakness_ranks_a_genuine_weak_link_above_a_strong_player(db_conn):
    _seed_teams_and_fixtures(db_conn)
    strong = _player(1, team_id=1, now_cost=100)
    weak = _player(2, team_id=1, now_cost=100)  # same price band as a much-better replacement
    better_replacement = _player(3, team_id=3, now_cost=100)
    squad = [strong, weak]
    candidate_pool = [strong, weak, better_replacement]

    projections = {
        1: {c.WEAKNESS_HORIZON_GWS: 12.0},  # strong player projects well
        2: {c.WEAKNESS_HORIZON_GWS: 3.0},   # weak player projects poorly
        3: {c.WEAKNESS_HORIZON_GWS: 11.0},  # a much better same-price replacement exists for the weak player
    }
    histories = {1: [_hist_row(gw, mins=90) for gw in range(1, 6)], 2: [_hist_row(gw, mins=90) for gw in range(1, 6)]}

    ranked = weakness.rank_squad_weakness(db_conn, squad, candidate_pool, projections, histories, current_gw=6)

    assert ranked[0].player["player_id"] == 2
    assert ranked[0].weakness_score > ranked[1].weakness_score
    assert ranked[0].fixture_swing > 0  # team 1's run got tougher, applies to both squad players equally
    assert ranked[0].replacement_gap > ranked[1].replacement_gap


def test_to_storage_rows_shape_and_1_indexed_rank():
    b1 = weakness.WeaknessBreakdown(player={"player_id": 1}, replacement_gap=1, form_decline=0, fixture_swing=0, minutes_risk=0, weakness_score=0.5)
    b2 = weakness.WeaknessBreakdown(player={"player_id": 2}, replacement_gap=2, form_decline=0, fixture_swing=0, minutes_risk=0, weakness_score=1.0)
    rows = weakness.to_storage_rows(1213466, 10, [b2, b1], computed_at="2026-01-01T00:00:00Z")
    assert rows[0] == (1213466, 10, 2, 2, 0, 0, 0, 1.0, 1, "2026-01-01T00:00:00Z")
    assert rows[1][8] == 2  # second row's rank


def test_dominant_reason_picks_the_largest_weighted_contributor():
    breakdown = weakness.WeaknessBreakdown(
        player={"player_id": 1}, replacement_gap=1.0, form_decline=10.0, fixture_swing=1.0, minutes_risk=1.0, weakness_score=0,
    )
    # form_decline's weight (0.25) * 10.0 dwarfs the others even though its raw value isn't the biggest input.
    assert weakness._dominant_reason(breakdown) == "form_decline"


# --- find_replacement_candidates / recommend_weak_link_transfer (Part 2) ---

def _weakness_scenario():
    squad = [
        _player(1, team_id=1, now_cost=100, sell_price=100),  # the weak link
        _player(2, team_id=2, now_cost=60, sell_price=60),
    ]
    pool = squad + [
        _player(101, team_id=3, now_cost=100, sell_price=100),  # affordable, better replacement for player 1
        _player(103, team_id=4, now_cost=150, sell_price=150),  # too expensive
    ]
    projections = {
        1: {c.WEAKNESS_HORIZON_GWS: 3.0},
        2: {c.WEAKNESS_HORIZON_GWS: 8.0},
        101: {c.WEAKNESS_HORIZON_GWS: 9.0},
        103: {c.WEAKNESS_HORIZON_GWS: 20.0},
    }
    return squad, pool, projections


def test_find_replacement_candidates_filters_position_budget_and_team_limit():
    squad, pool, projections = _weakness_scenario()
    weak_link = squad[0]
    candidates = weakness.find_replacement_candidates(weak_link, squad, pool, bank=10, projections=projections)

    candidate_ids = [cand["player_id"] for cand, _, _ in candidates]
    assert 101 in candidate_ids  # affordable, clears the bar
    assert 103 not in candidate_ids  # too expensive (cost_delta 50 > bank 10)
    assert candidates[0][0]["player_id"] == 101  # best net_gain first


def test_recommend_weak_link_transfer_returns_top_pick_for_the_weakest_player():
    squad, pool, projections = _weakness_scenario()
    ranked = [
        weakness.WeaknessBreakdown(player=squad[0], replacement_gap=6, form_decline=0, fixture_swing=0, minutes_risk=0, weakness_score=3.0),
        weakness.WeaknessBreakdown(player=squad[1], replacement_gap=0, form_decline=0, fixture_swing=0, minutes_risk=0, weakness_score=0.0),
    ]
    rec = weakness.recommend_weak_link_transfer(ranked, squad, pool, bank=10, free_transfers=1, projections=projections)

    assert rec is not None
    assert rec.weak_link.player["player_id"] == 1
    assert rec.replacement["player_id"] == 101
    assert rec.hit_cost == 0  # covered by the 1 free transfer


def test_recommend_weak_link_transfer_falls_back_when_the_weakest_player_has_nothing_worth_doing():
    squad = [
        _player(1, team_id=1, now_cost=100, sell_price=100),  # ranked weakest, but no upgrade exists
        _player(2, team_id=2, now_cost=60, sell_price=60),    # ranked 2nd, has a real upgrade available
    ]
    pool = squad + [_player(201, team_id=3, now_cost=60, sell_price=60)]
    projections = {
        1: {c.WEAKNESS_HORIZON_GWS: 10.0},  # already near the ceiling, nothing beats it
        2: {c.WEAKNESS_HORIZON_GWS: 2.0},
        201: {c.WEAKNESS_HORIZON_GWS: 9.0},  # clear upgrade over player 2
    }
    ranked = [
        weakness.WeaknessBreakdown(player=squad[0], replacement_gap=0, form_decline=0, fixture_swing=0, minutes_risk=0, weakness_score=5.0),
        weakness.WeaknessBreakdown(player=squad[1], replacement_gap=0, form_decline=0, fixture_swing=0, minutes_risk=0, weakness_score=1.0),
    ]
    rec = weakness.recommend_weak_link_transfer(ranked, squad, pool, bank=10, free_transfers=1, projections=projections)

    assert rec is not None
    assert rec.weak_link.player["player_id"] == 2  # fell back past the #1-ranked weak link


def test_recommend_weak_link_transfer_requires_margin_to_clear_a_hit():
    squad = [_player(1, team_id=1, now_cost=100, sell_price=100)]
    pool = squad + [_player(101, team_id=2, now_cost=100, sell_price=100)]
    projections = {1: {c.WEAKNESS_HORIZON_GWS: 5.0}, 101: {c.WEAKNESS_HORIZON_GWS: 8.0}}  # net_gain 3.0, short of 4 * 1.5 = 6
    ranked = [weakness.WeaknessBreakdown(player=squad[0], replacement_gap=0, form_decline=0, fixture_swing=0, minutes_risk=0, weakness_score=1.0)]

    rec = weakness.recommend_weak_link_transfer(ranked, squad, pool, bank=10, free_transfers=0, projections=projections)
    assert rec is None


def test_recommend_weak_link_transfer_returns_none_when_nothing_clears_the_bar():
    squad = [_player(1, team_id=1, now_cost=100, sell_price=100)]
    pool = squad
    projections = {1: {c.WEAKNESS_HORIZON_GWS: 10.0}}
    ranked = [weakness.WeaknessBreakdown(player=squad[0], replacement_gap=0, form_decline=0, fixture_swing=0, minutes_risk=0, weakness_score=1.0)]

    rec = weakness.recommend_weak_link_transfer(ranked, squad, pool, bank=10, free_transfers=1, projections=projections)
    assert rec is None
