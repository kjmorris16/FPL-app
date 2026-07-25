"""Estimate a player's minutes-probability distribution for an upcoming fixture."""
from src.scoring import constants as c


def availability_multiplier(status: str | None, chance_of_playing_next_round: float | None) -> float:
    """0-1 multiplier reflecting injury/suspension/fitness-doubt status.

    FPL sets `chance_of_playing_next_round` (0-100) whenever there's a fitness
    doubt; it's None when there's no doubt, in which case we fall back to the
    coarser `status` flag.
    """
    if chance_of_playing_next_round is not None:
        return chance_of_playing_next_round / 100
    if status in c.STATUS_UNAVAILABLE:
        return 0.0
    if status == c.DOUBTFUL_STATUS:
        return c.DEFAULT_DOUBTFUL_MULTIPLIER
    return 1.0


def starts_ratio(history_rows: list[dict], window: int = c.RECENT_WINDOW_GWS) -> float | None:
    """Fraction of recent gameweeks in which the player played 60+ minutes.

    `history_rows` must be sorted ascending by gameweek. Returns None if there's
    no history to compute a ratio from.
    """
    recent = history_rows[-window:]
    if not recent:
        return None
    starts = sum(1 for r in recent if (r.get("minutes") or 0) >= 60)
    return starts / len(recent)


def probabilities_from_starts_ratio(starts_ratio_value: float, availability_mult: float) -> tuple[float, float, float]:
    """Returns (p_60_plus, p_short_cameo, p_zero) for one upcoming fixture."""
    p60 = max(0.0, min(1.0, starts_ratio_value * availability_mult))
    p_short = (1 - p60) * c.SHORT_APPEARANCE_SHARE
    p_zero = 1 - p60 - p_short
    return p60, p_short, p_zero


def expected_minutes(p60: float, p_short: float) -> float:
    return p60 * 90 + p_short * c.SHORT_APPEARANCE_AVG_MINUTES
