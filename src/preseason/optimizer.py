"""Full-squad selector: picks the best possible 15-man squad from scratch
under FPL's budget/position/team constraints.

Unlike Phase 3's transfer optimizer -- which only ever evaluates small swaps
against an *existing* squad, and explicitly uses a shortlisting heuristic
rather than an exhaustive search -- building a full 15 from ~700 candidates
with no starting point is exactly the kind of constrained combinatorial
problem a real solver handles cleanly and optimally. This uses a mixed
-integer linear program (PuLP + its bundled CBC solver) rather than a greedy
heuristic, since the problem size (~700 binary variables, a handful of
constraints) solves in well under a second.
"""
import pulp

from src.preseason import constants as c


def select_best_squad(
    candidates: list[dict],
    budget: int = c.DEFAULT_BUDGET_TENTHS,
    must_include_ids: set[int] | None = None,
    must_exclude_ids: set[int] | None = None,
) -> list[dict]:
    """`candidates`: dicts with player_id, element_type, team_id, now_cost,
    and score (maximized, in tenths-of-a-million cost units matching
    `now_cost`). Returns the selected 15 as a list of the same dicts.

    `must_include_ids`/`must_exclude_ids` let a user force specific players
    in or out and have the solver re-optimize everyone else around that --
    rather than a free-form edit of the result table, which could easily
    violate the budget/position/team-cap constraints on its own. A
    contradictory or over-constrained request (e.g. excluding so many
    defenders that 5 can't be filled) surfaces as the same infeasibility
    error as a too-small budget, rather than a silent wrong answer.
    """
    must_include_ids = must_include_ids or set()
    must_exclude_ids = must_exclude_ids or set()

    problem = pulp.LpProblem("preseason_squad", pulp.LpMaximize)
    player_ids = [p["player_id"] for p in candidates]
    choice = pulp.LpVariable.dicts("pick", player_ids, cat="Binary")

    problem += pulp.lpSum(p["score"] * choice[p["player_id"]] for p in candidates)

    for position, count in c.SQUAD_COMPOSITION.items():
        problem += pulp.lpSum(choice[p["player_id"]] for p in candidates if p["element_type"] == position) == count

    problem += pulp.lpSum(p["now_cost"] * choice[p["player_id"]] for p in candidates) <= budget

    for team_id in {p["team_id"] for p in candidates}:
        problem += pulp.lpSum(choice[p["player_id"]] for p in candidates if p["team_id"] == team_id) <= c.MAX_PLAYERS_PER_TEAM

    for player_id in must_include_ids:
        if player_id in choice:
            problem += choice[player_id] == 1
    for player_id in must_exclude_ids:
        if player_id in choice:
            problem += choice[player_id] == 0

    problem.solve(pulp.PULP_CBC_CMD(msg=False))

    status = pulp.LpStatus[problem.status]
    if status != "Optimal":
        raise RuntimeError(f"No feasible squad found within budget £{budget / 10:.1f}m (solver status: {status})")

    return [p for p in candidates if choice[p["player_id"]].value() == 1]


def score_percentage(squad_score: float, baseline_score: float) -> float:
    """Squad quality as a percentage of `baseline_score` -- the best score
    achievable for the same budget with no must-include/exclude constraints.
    100% means the squad is the true optimum; it drops below 100% only when
    a must-include/exclude pick forces the solver away from that optimum.
    The raw summed score has no natural ceiling on its own (it's just
    projected points across a few gameweeks), so a percentage against "the
    best you could have chosen" is far more legible than that number alone.
    """
    if not baseline_score:
        return 0.0
    return round(squad_score / baseline_score * 100, 1)


def select_starting_xi(squad: list[dict]) -> dict:
    """Picks the highest-scoring valid starting XI from the 15-man squad
    across FPL's allowed formations. Returns {formation, starting_xi, bench}
    (bench ordered reserve-GK-first, then descending score -- the usual FPL
    bench-order convention)."""
    goalkeepers = sorted((p for p in squad if p["element_type"] == c.GK), key=lambda p: p["score"], reverse=True)
    defenders = sorted((p for p in squad if p["element_type"] == c.DEF), key=lambda p: p["score"], reverse=True)
    midfielders = sorted((p for p in squad if p["element_type"] == c.MID), key=lambda p: p["score"], reverse=True)
    forwards = sorted((p for p in squad if p["element_type"] == c.FWD), key=lambda p: p["score"], reverse=True)

    starting_gk = goalkeepers[0]

    best_shape, best_total, best_lineup = None, None, None
    for d, m, f in c.VALID_FORMATIONS:
        if d > len(defenders) or m > len(midfielders) or f > len(forwards):
            continue
        lineup = defenders[:d] + midfielders[:m] + forwards[:f]
        total = starting_gk["score"] + sum(p["score"] for p in lineup)
        if best_total is None or total > best_total:
            best_shape, best_total, best_lineup = (d, m, f), total, lineup

    starting_xi = [starting_gk] + best_lineup
    starting_ids = {p["player_id"] for p in starting_xi}
    bench = [p for p in squad if p["player_id"] not in starting_ids]
    bench_gk = [p for p in bench if p["element_type"] == c.GK]
    bench_outfield = sorted((p for p in bench if p["element_type"] != c.GK), key=lambda p: p["score"], reverse=True)

    return {
        "formation": f"{best_shape[0]}-{best_shape[1]}-{best_shape[2]}",
        "starting_xi": starting_xi,
        "bench": bench_gk + bench_outfield,
    }
