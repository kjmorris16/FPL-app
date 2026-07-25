from src.transfers import constants as c, optimizer


def _player(player_id, element_type, team_id, sell_price=None, now_cost=None):
    p = {"player_id": player_id, "element_type": element_type, "team_id": team_id, "web_name": f"P{player_id}"}
    if sell_price is not None:
        p["sell_price"] = sell_price
    if now_cost is not None:
        p["now_cost"] = now_cost
    return p


def test_team_counts():
    squad = [_player(1, c.FWD, 10), _player(2, c.FWD, 10), _player(3, c.DEF, 20)]
    counts = optimizer._team_counts(squad)
    assert counts == {10: 2, 20: 1}


def test_respects_team_limit_allows_under_cap():
    counts = {10: 2}
    assert optimizer._respects_team_limit(counts, [(20, 10)])  # 10 goes to 3, still ok


def test_respects_team_limit_blocks_over_cap():
    counts = {10: 3}
    assert not optimizer._respects_team_limit(counts, [(20, 10)])  # would push to 4


def test_respects_team_limit_same_team_swap_is_neutral():
    counts = {10: 3}
    assert optimizer._respects_team_limit(counts, [(10, 10)])  # replacing a team-10 player with another team-10 player


def test_hit_cost_free_transfers_cover_it():
    assert optimizer._hit_cost(num_transfers=1, free_transfers=1) == 0
    assert optimizer._hit_cost(num_transfers=2, free_transfers=2) == 0


def test_hit_cost_charges_for_excess_transfers():
    assert optimizer._hit_cost(num_transfers=2, free_transfers=1) == 4
    assert optimizer._hit_cost(num_transfers=2, free_transfers=0) == 8


def test_worth_the_hit_no_hits_always_true():
    assert optimizer._worth_the_hit(gain_at_hit_horizon=0, num_hits=0)


def test_worth_the_hit_requires_margin_above_cost():
    assert not optimizer._worth_the_hit(gain_at_hit_horizon=4, num_hits=1)  # exactly the cost, not enough
    assert not optimizer._worth_the_hit(gain_at_hit_horizon=5, num_hits=1)  # short of 1.5x margin
    assert optimizer._worth_the_hit(gain_at_hit_horizon=6, num_hits=1)  # clears 4 * 1.5 = 6


def test_worth_the_hit_scales_with_number_of_hits():
    assert not optimizer._worth_the_hit(gain_at_hit_horizon=11, num_hits=2)  # needs 8 * 1.5 = 12
    assert optimizer._worth_the_hit(gain_at_hit_horizon=12, num_hits=2)


def _squad_and_pool_scenario():
    """A small 3-player squad (one FWD, one DEF, one GK) with a pool of
    replacement candidates of varying value and affordability."""
    squad = [
        _player(1, c.FWD, team_id=10, sell_price=90),
        _player(2, c.DEF, team_id=20, sell_price=50),
        _player(3, c.GK, team_id=30, sell_price=45),
    ]
    pool = [
        # Same position as squad player 1 (FWD), better, affordable.
        _player(101, c.FWD, team_id=40, now_cost=95),
        # Same position as squad player 1 (FWD), better, too expensive.
        _player(102, c.FWD, team_id=40, now_cost=200),
        # Same position as squad player 1 (FWD), worse projection -- shouldn't be suggested.
        _player(103, c.FWD, team_id=40, now_cost=80),
        # Same position as squad player 2 (DEF), better, affordable, but from an
        # already-full team (team_id=50 already has 3 players elsewhere in a
        # bigger squad -- simulated via team_counts override in the team-limit test).
        _player(104, c.DEF, team_id=50, now_cost=55),
        # Same position as squad player 3 (GK), better, affordable.
        _player(105, c.GK, team_id=60, now_cost=48),
    ]
    projections = {
        1: {1: 4.0, 3: 10.0, 5: 15.0},
        2: {1: 3.0, 3: 8.0, 5: 12.0},
        3: {1: 3.0, 3: 7.0, 5: 10.0},
        101: {1: 6.0, 3: 16.0, 5: 24.0},  # clear upgrade on player 1
        102: {1: 8.0, 3: 20.0, 5: 30.0},  # even better, but unaffordable
        103: {1: 3.0, 3: 7.0, 5: 9.0},  # worse than player 1 -- should be filtered
        104: {1: 4.5, 3: 11.0, 5: 16.0},  # upgrade on player 2
        105: {1: 4.0, 3: 9.5, 5: 13.0},  # upgrade on player 3
    }
    return squad, pool, projections


def test_single_swap_candidates_filters_position_budget_and_gain():
    squad, pool, projections = _squad_and_pool_scenario()
    out_player = squad[0]  # FWD, sell_price=90
    squad_ids = {p["player_id"] for p in squad}
    team_counts = optimizer._team_counts(squad)

    candidates = optimizer._single_swap_candidates_for(
        out_player, pool, squad_ids, team_counts, budget=20, projections=projections, horizons=c.REPORTED_HORIZONS_GWS
    )

    candidate_ids = {cand.in_player["player_id"] for cand in candidates}
    assert candidate_ids == {101}  # 102 too expensive, 103 worse, 104/105 wrong position


def test_single_swap_candidates_sorted_best_first():
    squad, pool, projections = _squad_and_pool_scenario()
    out_player = squad[0]
    squad_ids = {p["player_id"] for p in squad}
    team_counts = optimizer._team_counts(squad)

    candidates = optimizer._single_swap_candidates_for(
        out_player, pool, squad_ids, team_counts, budget=200, projections=projections, horizons=c.REPORTED_HORIZONS_GWS
    )
    assert [cand.in_player["player_id"] for cand in candidates] == [102, 101]


def test_single_swap_candidates_blocks_team_limit_violation():
    squad, pool, projections = _squad_and_pool_scenario()
    out_player = squad[1]  # DEF
    squad_ids = {p["player_id"] for p in squad}
    team_counts = {50: 3}  # team 50 already at the cap

    candidates = optimizer._single_swap_candidates_for(
        out_player, pool, squad_ids, team_counts, budget=200, projections=projections, horizons=c.REPORTED_HORIZONS_GWS
    )
    assert all(cand.in_player["player_id"] != 104 for cand in candidates)


def test_generate_combos_always_includes_baseline():
    squad, pool, projections = _squad_and_pool_scenario()
    combos = optimizer.generate_combos(squad, pool, bank=0, free_transfers=1, projections=projections)
    assert any(len(combo.swaps) == 0 for combo in combos)


def test_generate_combos_ranks_best_single_swap_first_when_affordable():
    squad, pool, projections = _squad_and_pool_scenario()
    combos = optimizer.generate_combos(squad, pool, bank=20, free_transfers=1, projections=projections)
    best = combos[0]
    assert len(best.swaps) == 1
    assert best.swaps[0].in_player["player_id"] == 101
    assert best.hit_cost == 0


def test_generate_combos_two_transfer_combo_requires_joint_budget():
    squad, pool, projections = _squad_and_pool_scenario()
    # Enough bank for the FWD upgrade (cost_delta=5) and the DEF upgrade
    # (cost_delta=5) together, but not for a second FWD upgrade at 200 cost.
    combos = optimizer.generate_combos(squad, pool, bank=10, free_transfers=2, projections=projections)
    two_transfer_combos = [combo for combo in combos if len(combo.swaps) == 2]
    assert len(two_transfer_combos) >= 1
    out_ids = {s.out_player["player_id"] for s in two_transfer_combos[0].swaps}
    assert out_ids == {1, 2}


def test_generate_combos_drops_hit_that_is_not_worth_it():
    squad, pool, projections = _squad_and_pool_scenario()
    # Only 0 free transfers, and the single best swap's 5-GW gain (24-15=9)
    # is below the 4*1.5=6 threshold... actually 9 > 6, so bump the scenario:
    # reduce gain to something below the margin by using a smaller-upgrade pool.
    tight_projections = dict(projections)
    tight_projections[101] = {1: 4.2, 3: 10.5, 5: 16.0}  # gain of 1.0 over player 1's 15.0
    combos = optimizer.generate_combos(squad, pool, bank=20, free_transfers=0, projections=tight_projections)
    # The only affordable upgrade doesn't clear the hit margin -> only baseline remains
    assert all(len(combo.swaps) == 0 for combo in combos)


def test_generate_combos_keeps_hit_that_clearly_is_worth_it():
    squad, pool, projections = _squad_and_pool_scenario()
    # gain of 24-15=9 over a single -4 hit; margin needed is 4*1.5=6, 9 clears it.
    combos = optimizer.generate_combos(squad, pool, bank=20, free_transfers=0, projections=projections)
    hit_combos = [combo for combo in combos if combo.hit_cost > 0]
    assert len(hit_combos) >= 1
    assert hit_combos[0].worth_the_hit


def test_generate_combos_remaining_bank_reflects_cost_delta():
    squad, pool, projections = _squad_and_pool_scenario()
    combos = optimizer.generate_combos(squad, pool, bank=20, free_transfers=1, projections=projections)
    best = combos[0]
    assert best.remaining_bank == 20 - best.swaps[0].cost_delta
