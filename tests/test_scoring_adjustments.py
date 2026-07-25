from src.scoring import adjustments


def test_attacking_multiplier_neutral_difficulty_is_one():
    assert adjustments.attacking_multiplier(3) == 1.0


def test_attacking_multiplier_easier_fixture_boosts_output():
    assert adjustments.attacking_multiplier(1) > 1.0
    assert adjustments.attacking_multiplier(1) == 1.2


def test_attacking_multiplier_harder_fixture_reduces_output():
    assert adjustments.attacking_multiplier(5) < 1.0
    assert adjustments.attacking_multiplier(5) == 0.8


def test_defensive_shots_multiplier_is_inverse_of_attacking():
    assert adjustments.defensive_shots_multiplier(3) == 1.0
    assert adjustments.defensive_shots_multiplier(5) == 1.2
    assert adjustments.defensive_shots_multiplier(1) == 0.8
