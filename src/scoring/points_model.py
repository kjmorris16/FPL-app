"""Combine minutes probability, underlying rates, and fixture context into an
expected-points figure for a single fixture, following FPL's actual
points-per-action rules by position.
"""
from src.scoring import constants as c


def fixture_points(
    element_type: int,
    p60: float,
    p_short: float,
    exp_minutes: float,
    xg90: float,
    xa90: float,
    saves90: float,
    clean_sheet_prob: float,
    expected_goals_conceded: float,
    atk_multiplier: float,
    def_multiplier: float,
    bonus90: float = 0.0,
) -> float:
    appearance_pts = p60 * c.APPEARANCE_POINTS_60_PLUS + p_short * c.APPEARANCE_POINTS_UNDER_60

    minutes_fraction = exp_minutes / 90
    exp_goals = xg90 * minutes_fraction * atk_multiplier
    exp_assists = xa90 * minutes_fraction * atk_multiplier

    goals_pts = exp_goals * c.GOAL_POINTS[element_type]
    assists_pts = exp_assists * c.ASSIST_POINTS

    clean_sheet_pts = 0.0
    if element_type in c.CLEAN_SHEET_POSITIONS:
        # Clean sheet points only count for players on the pitch 60+ minutes.
        clean_sheet_pts = p60 * clean_sheet_prob * c.CLEAN_SHEET_POINTS[element_type]

    conceded_pts = 0.0
    if element_type in c.GOALS_CONCEDED_POSITIONS:
        conceded_pts = p60 * expected_goals_conceded * c.GOALS_CONCEDED_POINTS_PER_GOAL

    saves_pts = 0.0
    if element_type in c.SAVE_POSITIONS:
        exp_saves = saves90 * minutes_fraction * def_multiplier
        saves_pts = exp_saves * c.SAVE_POINTS_PER_SAVE

    bonus_pts = bonus90 * minutes_fraction

    return (
        appearance_pts
        + goals_pts
        + assists_pts
        + clean_sheet_pts
        + conceded_pts
        + saves_pts
        + bonus_pts
    )
