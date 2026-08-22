"""Core expected-points (xPts) engine.

Combines minutes probability, blended underlying stats (xG90/xA90/saves90),
clean-sheet modelling from team strength, and fixture difficulty into a
per-gameweek points projection for every player. Projections are computed one
gameweek at a time and stored in `player_projections`; the 1/3/5-gameweek
horizon figures used elsewhere are just sums over consecutive rows (see
`data_access.get_horizon_projection`).
"""
import logging
from datetime import datetime, timezone

from src.db import connection
from src.scoring import adjustments, clean_sheets, confidence, constants as c, data_access, minutes, points_model, underlying

logger = logging.getLogger(__name__)

DEFAULT_HORIZON_GWS = 5

_RATE_STATS = (("xg90", "expected_goals"), ("xa90", "expected_assists"), ("saves90", "saves"), ("bonus90", "bonus"))
_PREV_RATE_STATS = _RATE_STATS
_FALLBACK_KEYS = ("starts_ratio", "xg90", "xa90", "saves90", "bonus90")


def _position_average_rates(players: list[dict], histories: dict[int, list[dict]]) -> tuple[dict[int, dict[str, float]], dict[int, bool]]:
    """element_type -> {"starts_ratio", "xg90", "xa90", "saves90", "bonus90"}
    league averages, computed only from players with enough current-season
    minutes to be a reliable data point -- plus, per position, whether any
    player actually cleared that bar. Early in a season (or before it
    starts) no one has, so every bucket is empty and every average is a
    meaningless 0.0; callers use the second dict to know when to fall back
    to something better than that same-season league average instead of
    trusting it at face value.
    """
    buckets = {et: {key: [] for key in _FALLBACK_KEYS} for et in c.ALL_POSITIONS}
    contributors = {et: 0 for et in c.ALL_POSITIONS}

    for player in players:
        hist = histories.get(player["id"], [])
        if underlying.total_minutes(hist) < c.NEW_PLAYER_MINUTES_THRESHOLD:
            continue
        et = player["element_type"]
        if et not in buckets:
            continue

        contributors[et] += 1
        ratio = minutes.starts_ratio(hist)
        if ratio is not None:
            buckets[et]["starts_ratio"].append(ratio)
        for key, stat in _RATE_STATS:
            rate = underlying.blended_per90(hist, stat)
            if rate is not None:
                buckets[et][key].append(rate)

    averages = {
        et: {key: (sum(values) / len(values) if values else 0.0) for key, values in stats.items()}
        for et, stats in buckets.items()
    }
    has_data = {et: contributors[et] > 0 for et in c.ALL_POSITIONS}
    return averages, has_data


def _previous_season_position_averages(players: list[dict], prev_stats: dict[int, dict]) -> dict[int, dict[str, float]]:
    """element_type -> {"starts_ratio", "xg90", "xa90", "saves90", "bonus90"}
    averages from LAST season, for players who played enough of it to be a
    reliable data point. This is the fallback baseline used when a player has
    neither enough current-season history nor their own previous-season
    record (rookies, promoted-team debuts, overseas signings)."""
    buckets = {et: {key: [] for key in _FALLBACK_KEYS} for et in c.ALL_POSITIONS}

    for player in players:
        stats = prev_stats.get(player["id"])
        if not stats or (stats.get("minutes") or 0) < c.PREVIOUS_SEASON_SHRINKAGE_MINUTES:
            continue
        et = player["element_type"]
        if et not in buckets:
            continue

        prev_minutes = stats["minutes"]
        buckets[et]["starts_ratio"].append(min(1.0, prev_minutes / c.FULL_SEASON_MINUTES))
        for key, stat in _PREV_RATE_STATS:
            buckets[et][key].append(underlying.per90_from_totals(stats.get(stat), prev_minutes))

    return {
        et: {key: (sum(values) / len(values) if values else 0.0) for key, values in stats.items()}
        for et, stats in buckets.items()
    }


def _previous_season_priors(players: list[dict], prev_stats: dict[int, dict], prev_pos_avg: dict[int, dict[str, float]]) -> dict[int, dict[str, float]]:
    """player_id -> {"starts_ratio", "xg90", "xa90", "saves90", "bonus90"}:
    each player's OWN previous-season rate, shrunk towards last season's
    position average by how much of last season they actually played. This
    is what makes the current-season fallback baseline player-specific
    (rather than one flat number per position) even when the current season
    has produced no data at all yet -- a proven 20-goal striker and a
    third-choice keeper get different fallback rates instead of identically
    collapsing to zero.
    """
    priors = {}
    for player in players:
        et = player["element_type"]
        pos_rates = prev_pos_avg.get(et, {key: 0.0 for key in _FALLBACK_KEYS})
        stats = prev_stats.get(player["id"])
        prev_minutes = (stats or {}).get("minutes") or 0

        raw_starts_ratio = min(1.0, prev_minutes / c.FULL_SEASON_MINUTES) if stats else None
        priors[player["id"]] = {
            "starts_ratio": underlying.shrink_to_position_average(
                raw_starts_ratio, prev_minutes, pos_rates["starts_ratio"], c.PREVIOUS_SEASON_SHRINKAGE_MINUTES
            ),
        }
        for key, stat in _PREV_RATE_STATS:
            raw_rate = underlying.per90_from_totals(stats.get(stat), prev_minutes) if stats else None
            priors[player["id"]][key] = underlying.shrink_to_position_average(
                raw_rate, prev_minutes, pos_rates[key], c.PREVIOUS_SEASON_SHRINKAGE_MINUTES
            )
    return priors


def _fallback_rates(players: list[dict], pos_avg: dict, pos_avg_has_data: dict[int, bool], player_priors: dict[int, dict[str, float]]) -> dict[int, dict[str, float]]:
    """player_id -> fallback rates fed into the current-season shrinkage
    estimator: the same-season league average where the current season
    actually has enough players to make that average meaningful, otherwise
    this player's own previous-season-informed prior."""
    fallback = {}
    for player in players:
        et = player["element_type"]
        pid = player["id"]
        fallback[pid] = pos_avg[et] if pos_avg_has_data.get(et) else player_priors[pid]
    return fallback


def _project_player_gw(player: dict, history: list[dict], team: dict, fixtures_this_gw: list[dict], teams: dict, league_avgs: dict, fallback: dict) -> tuple[float, float]:
    element_type = player["element_type"]
    mins_hist = underlying.total_minutes(history)

    raw_starts_ratio = minutes.starts_ratio(history)
    starts_ratio = underlying.shrink_to_position_average(raw_starts_ratio, mins_hist, fallback["starts_ratio"])
    availability = minutes.availability_multiplier(player["status"], player["chance_of_playing_next_round"])

    xg90 = underlying.shrink_to_position_average(
        underlying.blended_per90(history, "expected_goals"), mins_hist, fallback["xg90"]
    )
    xa90 = underlying.shrink_to_position_average(
        underlying.blended_per90(history, "expected_assists"), mins_hist, fallback["xa90"]
    )
    saves90 = 0.0
    if element_type == c.GK:
        saves90 = underlying.shrink_to_position_average(
            underlying.blended_per90(history, "saves"), mins_hist, fallback["saves90"]
        )
    bonus90 = underlying.shrink_to_position_average(
        underlying.blended_per90(history, "bonus"), mins_hist, fallback["bonus90"]
    )

    total_points = 0.0
    for fixture in fixtures_this_gw:
        p60, p_short, _ = minutes.probabilities_from_starts_ratio(starts_ratio, availability)
        exp_minutes = minutes.expected_minutes(p60, p_short)

        opponent = teams.get(fixture["opponent_team"], {})
        difficulty = fixture["difficulty"] or c.FIXTURE_DIFFICULTY_NEUTRAL
        atk_mult = adjustments.attacking_multiplier(difficulty)
        def_mult = adjustments.defensive_shots_multiplier(difficulty)

        exp_conceded = clean_sheets.expected_goals_conceded(team, opponent, fixture["is_home"], league_avgs)
        cs_prob = clean_sheets.clean_sheet_probability(exp_conceded)

        total_points += points_model.fixture_points(
            element_type, p60, p_short, exp_minutes, xg90, xa90, saves90,
            cs_prob, exp_conceded, atk_mult, def_mult, bonus90,
        )

    conf = confidence.confidence_score(mins_hist)
    return total_points, conf


def compute_projections(conn, start_gw: int, horizon_gws: int = DEFAULT_HORIZON_GWS, as_of_gw: int | None = None) -> list[tuple]:
    """Compute per-gameweek projections for every player across
    [start_gw, start_gw + horizon_gws - 1].

    `as_of_gw` restricts player history to gameweeks strictly before it, so
    the backtest can recreate what the model would have projected at that
    point in the season without look-ahead bias.

    Returns rows ready for `data_access.upsert_projections`.
    """
    players = data_access.get_players(conn)
    teams = data_access.get_teams(conn)
    league_avgs = clean_sheets.league_strength_averages(teams.values())
    histories = data_access.get_all_player_histories(conn, as_of_gw=as_of_gw)
    pos_avg, pos_avg_has_data = _position_average_rates(players, histories)

    # Previous-season data gives each player a differentiated fallback
    # baseline for the shrinkage estimator, so early-season projections (or
    # any player who's individually still new to this season) don't all
    # collapse to the same same-season league average -- which is itself
    # meaningless (0.0 for every position) before the current season has
    # produced any gameweek_stats at all.
    prev_stats = data_access.get_previous_season_stats(conn)
    prev_pos_avg = _previous_season_position_averages(players, prev_stats)
    player_priors = _previous_season_priors(players, prev_stats, prev_pos_avg)
    fallback_rates = _fallback_rates(players, pos_avg, pos_avg_has_data, player_priors)

    end_gw = start_gw + horizon_gws - 1
    fixtures_map = data_access.get_team_fixtures_map(conn, start_gw, end_gw)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for player in players:
        team = teams.get(player["team_id"])
        if team is None:
            continue
        history = histories.get(player["id"], [])
        team_fixtures = fixtures_map.get(player["team_id"], {})

        for gw in range(start_gw, end_gw + 1):
            fixtures_this_gw = team_fixtures.get(gw, [])
            if not fixtures_this_gw:
                # Blank gameweek: no fixture means a certain zero, not a low-confidence guess.
                rows.append((player["id"], gw, 0.0, 1.0, now))
                continue
            pts, conf = _project_player_gw(
                player, history, team, fixtures_this_gw, teams, league_avgs, fallback_rates[player["id"]]
            )
            rows.append((player["id"], gw, round(pts, 2), round(conf, 3), now))
    return rows


def run(start_gw: int | None = None, horizon_gws: int = DEFAULT_HORIZON_GWS) -> int:
    with connection() as conn:
        if start_gw is None:
            start_gw = data_access.get_current_gw(conn)
        rows = compute_projections(conn, start_gw, horizon_gws)
        data_access.upsert_projections(conn, rows)
    logger.info("Computed projections for gameweeks %d-%d", start_gw, start_gw + horizon_gws - 1)
    return start_gw


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
