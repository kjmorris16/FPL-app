"""Ranks candidate transfer combinations (0, 1, or 2 transfers) by projected
point gain, respecting squad composition, per-team, and budget constraints,
and gates any hit-taking combo behind a "clearly worth it" margin.

Only same-position replacements are considered (an outgoing player's
element_type must match the incoming player's). FPL doesn't actually require
this -- you could transfer a DEF for a MID as long as the resulting 15 still
satisfies 2-5-5-3 -- but cross-position swaps would need to re-balance
multiple players per transfer to keep the squad legal, a much bigger search
problem for limited extra value. Documented simplification, not a rule of
the game itself.

Two-transfer combos are built from each outgoing player's own shortlist of
best single replacements, then paired up and re-checked for joint budget and
team-limit validity -- not an exhaustive search over every possible pair of
replacements (see `TOP_SINGLE_SWAPS_PER_PLAYER` in constants.py). This can
miss a combo where pooling two players' sale proceeds unlocks an upgrade
that's unaffordable alone; the shortlisting step uses a generous budget cap
to reduce (not eliminate) that risk, while the combo-assembly step always
re-checks the *exact* joint budget before a combo is returned.
"""
from dataclasses import dataclass

from src.transfers import constants as c


@dataclass
class SwapCandidate:
    out_player: dict
    in_player: dict
    cost_delta: int  # tenths of a million; positive = costs more than the sale nets
    gains: dict  # horizon (GWs) -> projected point gain (in - out)


@dataclass
class TransferCombo:
    swaps: list  # list[SwapCandidate]; empty = "make no transfers"
    gains: dict  # horizon -> summed gain across swaps
    hit_cost: int  # points deducted (0, 4, 8, ...)
    net_gains: dict  # horizon -> gains - hit_cost
    remaining_bank: int
    worth_the_hit: bool  # always True when hit_cost == 0


def _team_counts(squad: list[dict]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for p in squad:
        counts[p["team_id"]] = counts.get(p["team_id"], 0) + 1
    return counts


def _apply_swaps_team_counts(counts: dict[int, int], swaps: list[tuple[int, int]]) -> dict[int, int]:
    new_counts = dict(counts)
    for out_team, in_team in swaps:
        new_counts[out_team] = new_counts.get(out_team, 0) - 1
        new_counts[in_team] = new_counts.get(in_team, 0) + 1
    return new_counts


def _respects_team_limit(counts: dict[int, int], swaps: list[tuple[int, int]], max_per_team: int = c.MAX_PLAYERS_PER_TEAM) -> bool:
    new_counts = _apply_swaps_team_counts(counts, swaps)
    return all(count <= max_per_team for count in new_counts.values())


def _single_swap_candidates_for(
    out_player: dict,
    candidate_pool: list[dict],
    squad_ids: set,
    team_counts: dict,
    budget: int,
    projections: dict,
    horizons: tuple,
) -> list[SwapCandidate]:
    """All valid, affordable, gain-positive replacements for one squad player,
    best-first by gain at the primary ranking horizon."""
    out_gains = projections.get(out_player["player_id"], {})
    candidates = []
    for in_player in candidate_pool:
        if in_player["player_id"] in squad_ids:
            continue
        if in_player["element_type"] != out_player["element_type"]:
            continue
        cost_delta = in_player["now_cost"] - out_player["sell_price"]
        if cost_delta > budget:
            continue
        if not _respects_team_limit(team_counts, [(out_player["team_id"], in_player["team_id"])]):
            continue

        in_gains = projections.get(in_player["player_id"], {})
        gains = {h: in_gains.get(h, 0.0) - out_gains.get(h, 0.0) for h in horizons}
        if gains[c.DEFAULT_RANKING_HORIZON_GWS] <= 0:
            continue

        candidates.append(SwapCandidate(out_player=out_player, in_player=in_player, cost_delta=cost_delta, gains=gains))

    candidates.sort(key=lambda cand: cand.gains[c.DEFAULT_RANKING_HORIZON_GWS], reverse=True)
    return candidates


def _hit_cost(num_transfers: int, free_transfers: int) -> int:
    return max(0, num_transfers - free_transfers) * c.HIT_COST


def _worth_the_hit(gain_at_hit_horizon: float, num_hits: int) -> bool:
    if num_hits == 0:
        return True
    return gain_at_hit_horizon >= c.HIT_COST * num_hits * c.HIT_MARGIN_MULTIPLIER


def _build_combo(swaps: list[SwapCandidate], bank: int, free_transfers: int, horizons: tuple) -> TransferCombo:
    gains = {h: sum(s.gains[h] for s in swaps) for h in horizons}
    hit_cost = _hit_cost(len(swaps), free_transfers)
    net_gains = {h: gains[h] - hit_cost for h in horizons}
    remaining_bank = bank - sum(s.cost_delta for s in swaps)
    num_hits = max(0, len(swaps) - free_transfers)
    worth_the_hit = _worth_the_hit(gains.get(c.HIT_DECISION_HORIZON_GWS, gains[max(horizons)]), num_hits)
    return TransferCombo(
        swaps=swaps, gains=gains, hit_cost=hit_cost, net_gains=net_gains,
        remaining_bank=remaining_bank, worth_the_hit=worth_the_hit,
    )


def generate_combos(
    squad: list[dict],
    candidate_pool: list[dict],
    bank: int,
    free_transfers: int,
    projections: dict,
    horizons: tuple = c.REPORTED_HORIZONS_GWS,
) -> list[TransferCombo]:
    """Rank 0/1/2-transfer combinations by net projected gain at the primary
    ranking horizon. Combos that take a hit and don't clear the "worth it"
    margin are dropped entirely rather than ranked low -- a hit that doesn't
    pay for itself isn't a recommendation, just noise.
    """
    squad_ids = {p["player_id"] for p in squad}
    team_counts = _team_counts(squad)

    combos = [_build_combo([], bank, free_transfers, horizons)]  # baseline: do nothing

    # Shortlist candidates per outgoing player using a generous budget cap (see
    # module docstring) so a swap that only becomes affordable when paired
    # with selling a second player isn't prematurely excluded. The exact
    # budget is re-checked below when combos are actually assembled.
    sell_prices = [p["sell_price"] for p in squad]
    pair_shortlist_budget = bank + (max(sell_prices) if sell_prices else 0)

    candidates_by_out: dict[int, list[SwapCandidate]] = {
        out_player["player_id"]: _single_swap_candidates_for(
            out_player, candidate_pool, squad_ids, team_counts, pair_shortlist_budget, projections, horizons
        )[: c.TOP_SINGLE_SWAPS_PER_PLAYER]
        for out_player in squad
    }

    for shortlist in candidates_by_out.values():
        for cand in shortlist:
            if cand.cost_delta <= bank:
                combos.append(_build_combo([cand], bank, free_transfers, horizons))

    out_ids = list(candidates_by_out.keys())
    for i in range(len(out_ids)):
        for j in range(i + 1, len(out_ids)):
            for cand1 in candidates_by_out[out_ids[i]]:
                for cand2 in candidates_by_out[out_ids[j]]:
                    if cand1.in_player["player_id"] == cand2.in_player["player_id"]:
                        continue
                    if cand1.cost_delta + cand2.cost_delta > bank:
                        continue
                    swap_teams = [
                        (cand1.out_player["team_id"], cand1.in_player["team_id"]),
                        (cand2.out_player["team_id"], cand2.in_player["team_id"]),
                    ]
                    if not _respects_team_limit(team_counts, swap_teams):
                        continue
                    combos.append(_build_combo([cand1, cand2], bank, free_transfers, horizons))

    playable = [combo for combo in combos if combo.hit_cost == 0 or combo.worth_the_hit]
    playable.sort(key=lambda combo: combo.net_gains[c.DEFAULT_RANKING_HORIZON_GWS], reverse=True)
    return playable
