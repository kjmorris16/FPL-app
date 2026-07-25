from src.scoring import constants as c, points_model


def test_nailed_striker_no_clean_sheet_involvement():
    pts = points_model.fixture_points(
        element_type=c.FWD,
        p60=1.0, p_short=0.0, exp_minutes=90,
        xg90=0.5, xa90=0.2, saves90=0.0,
        clean_sheet_prob=0.4, expected_goals_conceded=1.2,
        atk_multiplier=1.0, def_multiplier=1.0, bonus90=0.5,
    )
    # appearance(2) + goals(0.5*4=2) + assists(0.2*3=0.6) + bonus(0.5) ; no CS, no conceded penalty
    expected = 2 + 2.0 + 0.6 + 0.5
    assert round(pts, 6) == round(expected, 6)


def test_forward_gets_no_clean_sheet_points():
    with_high_cs_prob = points_model.fixture_points(
        element_type=c.FWD, p60=1.0, p_short=0.0, exp_minutes=90,
        xg90=0.0, xa90=0.0, saves90=0.0,
        clean_sheet_prob=0.99, expected_goals_conceded=0.0,
        atk_multiplier=1.0, def_multiplier=1.0,
    )
    assert with_high_cs_prob == c.APPEARANCE_POINTS_60_PLUS


def test_defender_gets_clean_sheet_and_goals_conceded_penalty():
    pts = points_model.fixture_points(
        element_type=c.DEF, p60=1.0, p_short=0.0, exp_minutes=90,
        xg90=0.0, xa90=0.0, saves90=0.0,
        clean_sheet_prob=0.5, expected_goals_conceded=2.0,
        atk_multiplier=1.0, def_multiplier=1.0,
    )
    # appearance(2) + CS(1.0 * 0.5 * 4 = 2.0) + conceded penalty (1.0 * 2.0 * -0.5 = -1.0)
    assert round(pts, 6) == round(2 + 2.0 - 1.0, 6)


def test_goalkeeper_gets_save_points():
    pts = points_model.fixture_points(
        element_type=c.GK, p60=1.0, p_short=0.0, exp_minutes=90,
        xg90=0.0, xa90=0.0, saves90=3.0,
        clean_sheet_prob=0.0, expected_goals_conceded=1.0,
        atk_multiplier=1.0, def_multiplier=1.0,
    )
    # appearance(2) + saves (3 saves * 1/3 = 1.0) + conceded penalty (1.0*1.0*-0.5=-0.5)
    assert round(pts, 6) == round(2 + 1.0 - 0.5, 6)


def test_midfielder_gets_small_clean_sheet_bonus():
    pts = points_model.fixture_points(
        element_type=c.MID, p60=1.0, p_short=0.0, exp_minutes=90,
        xg90=0.0, xa90=0.0, saves90=0.0,
        clean_sheet_prob=1.0, expected_goals_conceded=0.0,
        atk_multiplier=1.0, def_multiplier=1.0,
    )
    assert round(pts, 6) == round(2 + 1 * c.CLEAN_SHEET_POINTS[c.MID], 6)


def test_zero_minutes_player_scores_zero():
    pts = points_model.fixture_points(
        element_type=c.MID, p60=0.0, p_short=0.0, exp_minutes=0,
        xg90=0.5, xa90=0.5, saves90=0.0,
        clean_sheet_prob=0.5, expected_goals_conceded=1.0,
        atk_multiplier=1.0, def_multiplier=1.0,
    )
    assert pts == 0.0


def test_easier_fixture_boosts_attacking_points():
    base_kwargs = dict(
        element_type=c.FWD, p60=1.0, p_short=0.0, exp_minutes=90,
        xg90=0.5, xa90=0.0, saves90=0.0,
        clean_sheet_prob=0.0, expected_goals_conceded=0.0, def_multiplier=1.0,
    )
    easy = points_model.fixture_points(**base_kwargs, atk_multiplier=1.2)
    hard = points_model.fixture_points(**base_kwargs, atk_multiplier=0.8)
    assert easy > hard
