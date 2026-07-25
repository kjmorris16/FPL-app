"""Clean-sheet probability and expected goals conceded, from team strength ratings.

Uses a simple Poisson model: expected goals conceded is scaled off a league
baseline by the attacking team's relative attack strength and the defending
team's relative defence strength (each split by home/away, as FPL's own team
strength ratings are). Clean-sheet probability is then P(X=0) for a Poisson
random variable with that expected value.
"""
import math

from src.scoring import constants as c

_STRENGTH_FIELDS = (
    "strength_attack_home",
    "strength_attack_away",
    "strength_defence_home",
    "strength_defence_away",
)


def league_strength_averages(teams) -> dict:
    teams = list(teams)
    averages = {}
    for field in _STRENGTH_FIELDS:
        values = [t[field] for t in teams if t.get(field)]
        averages[field] = sum(values) / len(values) if values else 1200.0
    return averages


def expected_goals_conceded(team: dict, opponent: dict, is_home: bool, league_avgs: dict) -> float:
    """Expected goals `team` concedes to `opponent` in this fixture (Poisson lambda)."""
    defence_key = "strength_defence_home" if is_home else "strength_defence_away"
    attack_key = "strength_attack_away" if is_home else "strength_attack_home"

    team_defence = team.get(defence_key) or league_avgs[defence_key]
    opp_attack = opponent.get(attack_key) or league_avgs[attack_key]

    relative_attack = opp_attack / league_avgs[attack_key]
    relative_defence = league_avgs[defence_key] / team_defence
    return c.BASE_GOALS_PER_TEAM_PER_GAME * relative_attack * relative_defence


def clean_sheet_probability(expected_conceded: float) -> float:
    return math.exp(-expected_conceded)
