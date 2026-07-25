import math

from src.scoring import clean_sheets


def _team(attack_home=1200, attack_away=1200, defence_home=1200, defence_away=1200):
    return {
        "strength_attack_home": attack_home,
        "strength_attack_away": attack_away,
        "strength_defence_home": defence_home,
        "strength_defence_away": defence_away,
    }


def test_league_strength_averages():
    teams = [_team(attack_home=1000), _team(attack_home=1400)]
    averages = clean_sheets.league_strength_averages(teams)
    assert averages["strength_attack_home"] == 1200


def test_league_strength_averages_falls_back_when_no_data():
    averages = clean_sheets.league_strength_averages([])
    assert averages["strength_attack_home"] == 1200.0


def test_expected_goals_conceded_neutral_teams_equals_baseline():
    league_avgs = clean_sheets.league_strength_averages([_team(), _team()])
    lam = clean_sheets.expected_goals_conceded(_team(), _team(), is_home=True, league_avgs=league_avgs)
    assert lam == 1.4  # BASE_GOALS_PER_TEAM_PER_GAME, both teams exactly average


def test_expected_goals_conceded_strong_defence_reduces_lambda():
    league_avgs = clean_sheets.league_strength_averages([_team(defence_home=1200), _team(defence_home=1200)])
    strong_defence_team = _team(defence_home=1600)
    weak_defence_team = _team(defence_home=800)

    lam_strong = clean_sheets.expected_goals_conceded(strong_defence_team, _team(), is_home=True, league_avgs=league_avgs)
    lam_weak = clean_sheets.expected_goals_conceded(weak_defence_team, _team(), is_home=True, league_avgs=league_avgs)
    assert lam_strong < lam_weak


def test_expected_goals_conceded_strong_opponent_attack_increases_lambda():
    league_avgs = clean_sheets.league_strength_averages([_team(), _team()])
    weak_attacker = _team(attack_away=800)
    strong_attacker = _team(attack_away=1600)

    lam_vs_weak = clean_sheets.expected_goals_conceded(_team(), weak_attacker, is_home=True, league_avgs=league_avgs)
    lam_vs_strong = clean_sheets.expected_goals_conceded(_team(), strong_attacker, is_home=True, league_avgs=league_avgs)
    assert lam_vs_strong > lam_vs_weak


def test_clean_sheet_probability_is_poisson_p_zero():
    assert clean_sheets.clean_sheet_probability(0.0) == 1.0
    assert clean_sheets.clean_sheet_probability(1.4) == math.exp(-1.4)
