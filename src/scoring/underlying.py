"""Per-90 underlying stats, blended from recent form and season-long totals.

Pure functions over plain gameweek_stats-shaped row dicts -- no DB access --
so they're trivial to unit test.
"""
from src.scoring import constants as c


def per90(rows: list[dict], stat_key: str, minutes_key: str = "minutes") -> float:
    total_stat = sum((r.get(stat_key) or 0) for r in rows)
    total_minutes = sum((r.get(minutes_key) or 0) for r in rows)
    if total_minutes <= 0:
        return 0.0
    return total_stat / total_minutes * 90


def blended_per90(
    history_rows: list[dict],
    stat_key: str,
    recent_window: int = c.RECENT_WINDOW_GWS,
    recent_weight: float = c.RECENT_FORM_WEIGHT,
) -> float | None:
    """Blend a recent rolling window with the season-long rate.

    `history_rows` must be sorted ascending by gameweek. Returns None if there
    is no history at all, so callers can distinguish "no data" from "data
    says zero".
    """
    if not history_rows:
        return None
    season_rate = per90(history_rows, stat_key)
    recent_rate = per90(history_rows[-recent_window:], stat_key)
    return recent_weight * recent_rate + (1 - recent_weight) * season_rate


def per90_from_totals(total_stat: float | int | None, total_minutes: int) -> float:
    """Same per-90 rate as `per90`, but from a single season-totals row (e.g.
    `player_previous_season_stats`) rather than a list of gameweek rows."""
    if not total_minutes:
        return 0.0
    return (total_stat or 0) / total_minutes * 90


def total_minutes(history_rows: list[dict]) -> int:
    return sum((r.get("minutes") or 0) for r in history_rows)


def shrink_to_position_average(
    individual_rate: float | None,
    minutes_played: int,
    position_avg_rate: float,
    full_confidence_minutes: int = c.NEW_PLAYER_MINUTES_THRESHOLD,
) -> float:
    """Shrinkage estimator: blend a player's own rate towards their position's
    league average, weighted by how much playing-time evidence we have for
    them. A brand new player (0 minutes) gets the pure position average; an
    established player (>= full_confidence_minutes) gets their own rate.
    """
    if full_confidence_minutes <= 0:
        weight = 1.0
    else:
        weight = min(1.0, minutes_played / full_confidence_minutes)
    individual = individual_rate if individual_rate is not None else 0.0
    return weight * individual + (1 - weight) * position_avg_rate
