"""Identifies the weakest player in a squad ("weak link") before searching
for a transfer, rather than ranking every possible swap equally.

**Part 1** (`rank_squad_weakness`) scores every squad player on how much
better a like-for-like replacement could realistically be
(`replacement_gap`), plus three data-driven warning signs -- declining
underlying form, a tougher-than-usual fixture run, and minutes/rotation risk
-- combined into a single `weakness_score` (weights in `constants.py`, so
they can be tuned once there's real results to compare against).

**Part 2** (`recommend_weak_link_transfer`) takes that ranked list and,
starting from the single weakest player, searches for the best affordable
same-position replacement -- falling back to the next-weakest player if no
replacement clears the hit-cost margin for the weakest one. This is a
complementary, single-player-focused recommendation that sits alongside (not
instead of) `optimizer.generate_combos`'s general N-transfer combination
search; both read the same squad/candidate-pool/projection inputs.

Minutes risk has no dedicated "new signing just arrived" data feed to draw
on, so it's approximated by a same-position teammate (from the whole
candidate pool, not just the squad) picking up notably more recent minutes
than this player -- this catches any rotation threat, a new arrival
included, without needing to identify transfers by name. Documented
simplification, not a claim of tracking actual squad-list news.
"""
from dataclasses import dataclass

from src.scoring import minutes, underlying
from src.transfers import constants as c, data_access, optimizer


@dataclass
class WeaknessBreakdown:
    player: dict
    replacement_gap: float
    form_decline: float
    fixture_swing: float
    minutes_risk: float
    weakness_score: float


@dataclass
class WeakLinkRecommendation:
    weak_link: WeaknessBreakdown
    weak_link_reason: str  # the modifier ("replacement_gap"/"form_decline"/"fixture_swing"/"minutes_risk") that contributed most
    replacement: dict
    net_gain: float
    cost_delta: int
    hit_cost: int


def compute_replacement_gap(own_projection: float, candidate_projections: list[float]) -> float:
    """`candidate_projections` is pre-filtered to same-position,
    similar-price-band, not-already-owned players (see `_price_band_candidates`).
    0.0 if no such candidate exists at all -- "no comparable option found" is
    not evidence this player is unusually strong, so it shouldn't push the
    weakness score negative.
    """
    if not candidate_projections:
        return 0.0
    return max(candidate_projections) - own_projection


def compute_form_decline(history: list[dict], window: int = c.FORM_DECLINE_WINDOW_GWS) -> float:
    """Positive = this player's recent xG90 + xA90 output has dropped below
    their own season-long rate (a meaningful decline); clamped to 0 when
    form is flat or improving. `history` must be sorted ascending by
    gameweek."""
    if not history:
        return 0.0
    recent = history[-window:]
    season_rate = underlying.per90(history, "expected_goals") + underlying.per90(history, "expected_assists")
    recent_rate = underlying.per90(recent, "expected_goals") + underlying.per90(recent, "expected_assists")
    return round(max(0.0, season_rate - recent_rate), 3)


def compute_fixture_swing(future_avg_difficulty: float | None, season_avg_difficulty: float | None) -> float:
    """Positive = the upcoming run is tougher than this player's
    season-average fixture difficulty so far; 0 if either side has no data
    to compare against (e.g. before GW1, or a blank-only stretch ahead)."""
    if future_avg_difficulty is None or season_avg_difficulty is None:
        return 0.0
    return round(max(0.0, future_avg_difficulty - season_avg_difficulty), 3)


def compute_minutes_risk(player: dict, history: list[dict], teammate_histories: list[list[dict]]) -> float:
    """0 (no signal) and up. Combines three data-driven signals:
    - **availability**: 1 minus the same status/chance_of_playing_next_round
      multiplier Phase 2's minutes model already uses (an injury/suspension
      flag maxes this out at 1.0).
    - **recent minutes trend**: how far this player's recent starts_ratio has
      fallen below their own season-long starts_ratio.
    - **teammate overtake**: how far a same-position teammate's recent
      starts_ratio now exceeds this player's, once that gap clears
      `MINUTES_RISK_TEAMMATE_OVERTAKE_MARGIN` (a small gap is normal
      week-to-week rotation, not a real threat).
    """
    availability = minutes.availability_multiplier(player["status"], player["chance_of_playing_next_round"])
    availability_risk = 1.0 - availability

    recent_ratio = minutes.starts_ratio(history)
    season_ratio = minutes.starts_ratio(history, window=len(history)) if history else None
    trend_risk = 0.0
    if recent_ratio is not None and season_ratio is not None:
        trend_risk = max(0.0, season_ratio - recent_ratio)

    overtake_risk = 0.0
    if recent_ratio is not None:
        teammate_ratios = [
            ratio for ratio in (minutes.starts_ratio(h) for h in teammate_histories) if ratio is not None
        ]
        best_teammate_ratio = max(teammate_ratios, default=0.0)
        gap = best_teammate_ratio - recent_ratio
        if gap >= c.MINUTES_RISK_TEAMMATE_OVERTAKE_MARGIN:
            overtake_risk = gap

    return round(availability_risk + trend_risk + overtake_risk, 3)


def compute_weakness_score(replacement_gap: float, form_decline: float, fixture_swing: float, minutes_risk: float) -> float:
    return round(
        c.WEAKNESS_REPLACEMENT_GAP_WEIGHT * replacement_gap
        + c.WEAKNESS_FORM_DECLINE_WEIGHT * form_decline
        + c.WEAKNESS_FIXTURE_SWING_WEIGHT * fixture_swing
        + c.WEAKNESS_MINUTES_RISK_WEIGHT * minutes_risk,
        3,
    )


def _price_band_candidates(player: dict, candidate_pool: list[dict], squad_ids: set) -> list[dict]:
    lo = player["now_cost"] - c.PRICE_BAND_TENTHS
    hi = player["now_cost"] + c.PRICE_BAND_TENTHS
    return [
        cand
        for cand in candidate_pool
        if cand["player_id"] not in squad_ids
        and cand["element_type"] == player["element_type"]
        and lo <= cand["now_cost"] <= hi
    ]


def rank_squad_weakness(
    conn,
    squad: list[dict],
    candidate_pool: list[dict],
    projections: dict[int, dict[int, float]],
    histories: dict[int, list[dict]],
    current_gw: int,
    horizon: int = c.WEAKNESS_HORIZON_GWS,
) -> list[WeaknessBreakdown]:
    """Part 1: every squad player, scored and ranked weakest-first.
    `projections` is `player_id -> {horizon: summed_projected_points}` (see
    `data_access.get_projection_totals`), already covering `horizon`.
    """
    squad_ids = {p["player_id"] for p in squad}

    # Same club + position, drawn from the whole candidate pool (not just the
    # squad) so a same-position teammate who isn't currently owned -- the
    # "new signing" case -- is visible to the minutes-risk check too.
    club_position_ids: dict[tuple[int, int], list[int]] = {}
    for cand in candidate_pool:
        club_position_ids.setdefault((cand["team_id"], cand["element_type"]), []).append(cand["player_id"])

    breakdowns = []
    for player in squad:
        history = histories.get(player["player_id"], [])
        own_projection = projections.get(player["player_id"], {}).get(horizon, 0.0)

        price_band_candidates = _price_band_candidates(player, candidate_pool, squad_ids)
        candidate_projections = [
            projections.get(cand["player_id"], {}).get(horizon, 0.0) for cand in price_band_candidates
        ]
        replacement_gap = compute_replacement_gap(own_projection, candidate_projections)

        form_decline = compute_form_decline(history)

        future_avg = data_access.get_average_fixture_difficulty(conn, player["team_id"], current_gw, horizon)
        season_avg = data_access.get_average_fixture_difficulty(conn, player["team_id"], 1, current_gw - 1)
        fixture_swing = compute_fixture_swing(future_avg, season_avg)

        teammate_ids = [
            pid
            for pid in club_position_ids.get((player["team_id"], player["element_type"]), [])
            if pid != player["player_id"]
        ]
        teammate_histories = [histories.get(pid, []) for pid in teammate_ids]
        minutes_risk = compute_minutes_risk(player, history, teammate_histories)

        weakness_score = compute_weakness_score(replacement_gap, form_decline, fixture_swing, minutes_risk)
        breakdowns.append(
            WeaknessBreakdown(
                player=player,
                replacement_gap=replacement_gap,
                form_decline=form_decline,
                fixture_swing=fixture_swing,
                minutes_risk=minutes_risk,
                weakness_score=weakness_score,
            )
        )

    breakdowns.sort(key=lambda b: b.weakness_score, reverse=True)
    return breakdowns


def to_storage_rows(manager_id: int, gw: int, ranked: list[WeaknessBreakdown], computed_at: str) -> list[tuple]:
    return [
        (
            manager_id, gw, b.player["player_id"], b.replacement_gap, b.form_decline,
            b.fixture_swing, b.minutes_risk, b.weakness_score, rank, computed_at,
        )
        for rank, b in enumerate(ranked, start=1)
    ]


def _dominant_reason(breakdown: WeaknessBreakdown) -> str:
    """Which weighted modifier contributed most to this player's
    weakness_score -- used to name one concrete reason in the rationale
    rather than dumping all four numbers on the reader."""
    contributions = {
        "replacement_gap": c.WEAKNESS_REPLACEMENT_GAP_WEIGHT * breakdown.replacement_gap,
        "form_decline": c.WEAKNESS_FORM_DECLINE_WEIGHT * breakdown.form_decline,
        "fixture_swing": c.WEAKNESS_FIXTURE_SWING_WEIGHT * breakdown.fixture_swing,
        "minutes_risk": c.WEAKNESS_MINUTES_RISK_WEIGHT * breakdown.minutes_risk,
    }
    return max(contributions, key=contributions.get)


def find_replacement_candidates(
    weak_link: dict,
    squad: list[dict],
    candidate_pool: list[dict],
    bank: int,
    projections: dict[int, dict[int, float]],
    horizon: int = c.WEAKNESS_HORIZON_GWS,
) -> list[tuple[dict, float, int]]:
    """All valid, affordable, gain-positive same-position replacements for
    `weak_link`: (candidate, net_gain, cost_delta) triples, best net_gain
    first. Respects the max-3-players-per-club rule via the same helpers
    `optimizer.generate_combos` uses, so both searches agree on what's legal.
    """
    squad_ids = {p["player_id"] for p in squad}
    team_counts = optimizer._team_counts(squad)
    out_gain = projections.get(weak_link["player_id"], {}).get(horizon, 0.0)

    results = []
    for candidate in candidate_pool:
        if candidate["player_id"] in squad_ids:
            continue
        if candidate["element_type"] != weak_link["element_type"]:
            continue
        cost_delta = candidate["now_cost"] - weak_link["sell_price"]
        if cost_delta > bank:
            continue
        if not optimizer._respects_team_limit(team_counts, [(weak_link["team_id"], candidate["team_id"])]):
            continue

        in_gain = projections.get(candidate["player_id"], {}).get(horizon, 0.0)
        net_gain = in_gain - out_gain
        if net_gain <= 0:
            continue

        results.append((candidate, net_gain, cost_delta))

    results.sort(key=lambda triple: triple[1], reverse=True)
    return results


def recommend_weak_link_transfer(
    ranked_weakness: list[WeaknessBreakdown],
    squad: list[dict],
    candidate_pool: list[dict],
    bank: int,
    free_transfers: int,
    projections: dict[int, dict[int, float]],
    horizon: int = c.WEAKNESS_HORIZON_GWS,
    max_candidates_tried: int = c.WEAK_LINK_CANDIDATES_TO_TRY,
) -> WeakLinkRecommendation | None:
    """Part 2: starting from the single weakest player, search for the best
    affordable same-position replacement. If the weakest player's best
    candidate doesn't clear the hit-cost margin (when a hit is needed),
    fall back to the next-weakest player instead of forcing a move on the
    worst-ranked player regardless of whether a good replacement exists.
    Returns None if nothing among the top `max_candidates_tried` clears the
    bar.
    """
    hit_cost = optimizer._hit_cost(num_transfers=1, free_transfers=free_transfers)

    for breakdown in ranked_weakness[:max_candidates_tried]:
        candidates = find_replacement_candidates(breakdown.player, squad, candidate_pool, bank, projections, horizon)
        if not candidates:
            continue
        best_candidate, net_gain, cost_delta = candidates[0]
        if hit_cost and not optimizer._worth_the_hit(net_gain, num_hits=1):
            continue
        return WeakLinkRecommendation(
            weak_link=breakdown,
            weak_link_reason=_dominant_reason(breakdown),
            replacement=best_candidate,
            net_gain=net_gain,
            cost_delta=cost_delta,
            hit_cost=hit_cost,
        )

    return None
