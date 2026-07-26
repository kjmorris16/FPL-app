import pytest

from src.preseason import constants as c, optimizer


def _candidate(player_id, element_type, team_id, score, cost):
    return {"player_id": player_id, "element_type": element_type, "team_id": team_id, "now_cost": cost, "score": score}


def _build_pool(gks, defs, mids, fwds):
    """Each arg is a list of (player_id, team_id, score, cost) tuples."""
    pool = []
    for pid, team_id, score, cost in gks:
        pool.append(_candidate(pid, c.GK, team_id, score, cost))
    for pid, team_id, score, cost in defs:
        pool.append(_candidate(pid, c.DEF, team_id, score, cost))
    for pid, team_id, score, cost in mids:
        pool.append(_candidate(pid, c.MID, team_id, score, cost))
    for pid, team_id, score, cost in fwds:
        pool.append(_candidate(pid, c.FWD, team_id, score, cost))
    return pool


def test_select_best_squad_respects_composition_and_picks_top_scorers_with_generous_budget():
    gks = [(1, 10, 5, 45), (2, 11, 4, 45), (3, 12, 3, 45)]
    defs = [(11 + i, 20 + i, 10 - i, 45) for i in range(6)]
    mids = [(21 + i, 30 + i, 10 - i, 45) for i in range(6)]
    fwds = [(31 + i, 40 + i, 10 - i, 45) for i in range(4)]
    pool = _build_pool(gks, defs, mids, fwds)

    squad = optimizer.select_best_squad(pool, budget=2000)

    assert len(squad) == 15
    ids = {p["player_id"] for p in squad}
    assert ids == {1, 2} | {11, 12, 13, 14, 15} | {21, 22, 23, 24, 25} | {31, 32, 33}
    # Lowest scorer in each group must be excluded.
    assert 3 not in ids
    assert 16 not in ids
    assert 26 not in ids
    assert 34 not in ids


def test_select_best_squad_respects_squad_composition_counts():
    gks = [(1, 10, 5, 45), (2, 11, 4, 45), (3, 12, 3, 45)]
    defs = [(11 + i, 20 + i, 10 - i, 45) for i in range(6)]
    mids = [(21 + i, 30 + i, 10 - i, 45) for i in range(6)]
    fwds = [(31 + i, 40 + i, 10 - i, 45) for i in range(4)]
    pool = _build_pool(gks, defs, mids, fwds)

    squad = optimizer.select_best_squad(pool, budget=2000)

    by_position = {}
    for p in squad:
        by_position.setdefault(p["element_type"], 0)
        by_position[p["element_type"]] += 1
    assert by_position == {c.GK: 2, c.DEF: 5, c.MID: 5, c.FWD: 3}


def test_select_best_squad_respects_team_cap():
    gks = [(1, 90, 5, 45), (2, 91, 4, 45)]
    # 4 defenders on the SAME team (all high scoring) plus 2 from another team.
    defs = [(11, 99, 10, 45), (12, 99, 9, 45), (13, 99, 8, 45), (14, 99, 7, 45), (15, 88, 6, 45), (16, 87, 5, 45)]
    mids = [(21 + i, 30 + i, 10 - i, 45) for i in range(5)]
    fwds = [(31 + i, 40 + i, 10 - i, 45) for i in range(3)]
    pool = _build_pool(gks, defs, mids, fwds)

    squad = optimizer.select_best_squad(pool, budget=2000)

    team_99_count = sum(1 for p in squad if p["team_id"] == 99)
    assert team_99_count <= c.MAX_PLAYERS_PER_TEAM

    def_ids = {p["player_id"] for p in squad if p["element_type"] == c.DEF}
    # Best 3 from team 99 (10, 9, 8) plus both from the other teams (6, 5) -- player 14 (score 7) must be dropped.
    assert def_ids == {11, 12, 13, 15, 16}


def test_select_best_squad_respects_budget_constraint():
    gks = [(1, 90, 1, 40), (2, 91, 1, 40)]
    mids = [(21 + i, 30 + i, 1, 40) for i in range(5)]
    fwds = [(31 + i, 40 + i, 1, 40) for i in range(3)]
    # 5 pricey high-scorers (cost 100 each) plus 1 cheap low-scorer (cost 10).
    # Unconstrained-by-budget optimum is the 5 pricey ones (total DEF cost 500);
    # a tight budget must force swapping the weakest pricey one for the cheap one.
    defs = [
        (11, 20, 15, 100), (12, 21, 14, 100), (13, 22, 13, 100), (14, 23, 12, 100), (15, 24, 11, 100),
        (16, 25, 1, 10),
    ]
    pool = _build_pool(gks, defs, mids, fwds)

    non_def_cost = 2 * 40 + 5 * 40 + 3 * 40  # GK + MID + FWD filler cost = 400
    # Budget only allows 4 of the 5 pricey defenders (400) + the cheap one (10): total DEF cost 410.
    budget = non_def_cost + 410

    squad = optimizer.select_best_squad(pool, budget=budget)
    total_cost = sum(p["now_cost"] for p in squad)
    assert total_cost <= budget

    def_ids = {p["player_id"] for p in squad if p["element_type"] == c.DEF}
    assert def_ids == {11, 12, 13, 14, 16}  # weakest pricey defender (15) swapped for the cheap filler (16)


def test_select_best_squad_raises_when_infeasible():
    gks = [(1, 90, 1, 45), (2, 91, 1, 45)]
    defs = [(11 + i, 20 + i, 1, 45) for i in range(5)]
    mids = [(21 + i, 30 + i, 1, 45) for i in range(5)]
    fwds = [(31 + i, 40 + i, 1, 45) for i in range(3)]
    pool = _build_pool(gks, defs, mids, fwds)

    with pytest.raises(RuntimeError, match="No feasible squad"):
        optimizer.select_best_squad(pool, budget=1)  # impossibly small


def test_select_best_squad_must_include_forces_a_player_in():
    gks = [(1, 10, 5, 45), (2, 11, 4, 45), (3, 12, 3, 45)]
    defs = [(11 + i, 20 + i, 10 - i, 45) for i in range(6)]
    mids = [(21 + i, 30 + i, 10 - i, 45) for i in range(6)]
    fwds = [(31 + i, 40 + i, 10 - i, 45) for i in range(4)]
    pool = _build_pool(gks, defs, mids, fwds)

    # Player 16 (the weakest DEF, score 5) would normally be excluded --
    # force it in and confirm the solver still returns a valid, optimal-given-
    # the-constraint squad rather than erroring or ignoring the request.
    squad = optimizer.select_best_squad(pool, budget=2000, must_include_ids={16})

    ids = {p["player_id"] for p in squad}
    assert 16 in ids
    def_ids = {p["player_id"] for p in squad if p["element_type"] == c.DEF}
    # Still the best 5 DEF given 16 is forced in: 16 plus the top 4 of the rest.
    assert def_ids == {11, 12, 13, 14, 16}


def test_select_best_squad_must_exclude_forces_a_player_out():
    gks = [(1, 10, 5, 45), (2, 11, 4, 45), (3, 12, 3, 45)]
    defs = [(11 + i, 20 + i, 10 - i, 45) for i in range(6)]
    mids = [(21 + i, 30 + i, 10 - i, 45) for i in range(6)]
    fwds = [(31 + i, 40 + i, 10 - i, 45) for i in range(4)]
    pool = _build_pool(gks, defs, mids, fwds)

    # Player 11 is normally the top DEF pick -- exclude it and confirm the
    # solver backfills with the next-best (12-15) instead.
    squad = optimizer.select_best_squad(pool, budget=2000, must_exclude_ids={11})

    ids = {p["player_id"] for p in squad}
    assert 11 not in ids
    def_ids = {p["player_id"] for p in squad if p["element_type"] == c.DEF}
    assert def_ids == {12, 13, 14, 15, 16}


def test_select_best_squad_must_include_and_exclude_together():
    gks = [(1, 10, 5, 45), (2, 11, 4, 45), (3, 12, 3, 45)]
    defs = [(11 + i, 20 + i, 10 - i, 45) for i in range(6)]
    mids = [(21 + i, 30 + i, 10 - i, 45) for i in range(6)]
    fwds = [(31 + i, 40 + i, 10 - i, 45) for i in range(4)]
    pool = _build_pool(gks, defs, mids, fwds)

    squad = optimizer.select_best_squad(pool, budget=2000, must_include_ids={16}, must_exclude_ids={11})

    ids = {p["player_id"] for p in squad}
    assert 16 in ids
    assert 11 not in ids
    def_ids = {p["player_id"] for p in squad if p["element_type"] == c.DEF}
    assert def_ids == {12, 13, 14, 15, 16}


def test_select_best_squad_contradictory_constraints_raise_infeasible():
    gks = [(1, 10, 5, 45), (2, 11, 4, 45), (3, 12, 3, 45)]
    defs = [(11 + i, 20 + i, 10 - i, 45) for i in range(6)]
    mids = [(21 + i, 30 + i, 10 - i, 45) for i in range(6)]
    fwds = [(31 + i, 40 + i, 10 - i, 45) for i in range(4)]
    pool = _build_pool(gks, defs, mids, fwds)

    with pytest.raises(RuntimeError, match="No feasible squad"):
        optimizer.select_best_squad(pool, budget=2000, must_include_ids={11}, must_exclude_ids={11})


def _squad_of_15(scores_by_pos):
    """scores_by_pos: {element_type: [scores...]} with exactly the right counts."""
    pool = []
    next_id = 1
    for et, scores in scores_by_pos.items():
        for i, score in enumerate(scores):
            pool.append(_candidate(next_id, et, 100 + next_id, score, 45))
            next_id += 1
    return pool


def test_select_starting_xi_picks_highest_scoring_valid_formation():
    squad = _squad_of_15({
        c.GK: [8, 2],
        c.DEF: [9, 8, 7, 1, 0.5],
        c.MID: [10, 9, 8, 7, 1],
        c.FWD: [12, 11, 1],
    })

    result = optimizer.select_starting_xi(squad)

    assert len(result["starting_xi"]) == 11
    assert len(result["bench"]) == 4
    # Best GK (score 8) should start; weaker GK (score 2) should be on the bench.
    starting_ids = {p["player_id"] for p in result["starting_xi"]}
    gk_starting = next(p for p in result["starting_xi"] if p["element_type"] == c.GK)
    assert gk_starting["score"] == 8

    d, m, f = (int(x) for x in result["formation"].split("-"))
    assert d + m + f == 10
    assert 3 <= d <= 5 and 2 <= m <= 5 and 1 <= f <= 3


def test_select_starting_xi_bench_has_reserve_gk_first():
    squad = _squad_of_15({
        c.GK: [8, 2],
        c.DEF: [9, 8, 7, 1, 0.5],
        c.MID: [10, 9, 8, 7, 1],
        c.FWD: [12, 11, 1],
    })
    result = optimizer.select_starting_xi(squad)
    assert result["bench"][0]["element_type"] == c.GK


def test_select_starting_xi_uses_all_11_highest_scorers_when_formation_allows():
    # With generous scores at every slot, the picked formation should be the
    # one maximizing total score across all valid (D, M, F) shapes.
    squad = _squad_of_15({
        c.GK: [8, 2],
        c.DEF: [9, 8, 7, 6, 5],
        c.MID: [10, 9, 8, 7, 6],
        c.FWD: [12, 11, 1],
    })
    result = optimizer.select_starting_xi(squad)
    starting_scores = sorted((p["score"] for p in result["starting_xi"]), reverse=True)
    # Sanity: the two weakest FWD/DEF/MID benched should be the lowest scorers overall.
    bench_scores = sorted(p["score"] for p in result["bench"])
    assert bench_scores[-1] <= min(starting_scores)


def test_score_percentage_is_100_when_squad_matches_baseline():
    assert optimizer.score_percentage(42.0, 42.0) == 100.0


def test_score_percentage_drops_below_100_when_squad_is_worse_than_baseline():
    assert optimizer.score_percentage(38.0, 40.0) == 95.0


def test_score_percentage_zero_baseline_is_zero_not_a_division_error():
    assert optimizer.score_percentage(0.0, 0.0) == 0.0


def test_score_percentage_rounds_to_one_decimal():
    assert optimizer.score_percentage(1.0, 3.0) == 33.3
