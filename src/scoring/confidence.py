"""Confidence scoring for projections, based on how much recent playing-time
evidence we have for a player. A projection built on 6 gameweeks of regular
starts is trustworthy; one for a player with almost no recent minutes (new
signing, long-term injury, fringe squad player) is much less so, even if the
point estimate looks similar.
"""
from src.scoring import constants as c


def confidence_score(
    minutes_played: int,
    full_confidence_minutes: int = c.FULL_CONFIDENCE_MINUTES,
    fallback: float = c.FALLBACK_CONFIDENCE_NO_HISTORY,
) -> float:
    if minutes_played <= 0:
        return fallback
    return min(1.0, minutes_played / full_confidence_minutes)


def horizon_confidence(gw_confidences: list[float]) -> float:
    if not gw_confidences:
        return 0.0
    return sum(gw_confidences) / len(gw_confidences)


def confidence_label(score: float) -> str:
    if score >= c.CONFIDENCE_HIGH_THRESHOLD:
        return "High"
    if score >= c.CONFIDENCE_MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"
