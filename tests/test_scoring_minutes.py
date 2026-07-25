from src.scoring import minutes


def test_availability_multiplier_uses_chance_of_playing_when_present():
    assert minutes.availability_multiplier("d", 75) == 0.75
    assert minutes.availability_multiplier("a", 50) == 0.5


def test_availability_multiplier_available_status_no_doubt():
    assert minutes.availability_multiplier("a", None) == 1.0


def test_availability_multiplier_unavailable_statuses_zero():
    for status in ("i", "s", "u", "n"):
        assert minutes.availability_multiplier(status, None) == 0.0


def test_availability_multiplier_doubtful_without_percentage_uses_default():
    assert minutes.availability_multiplier("d", None) == 0.75


def test_starts_ratio_none_for_empty_history():
    assert minutes.starts_ratio([]) is None


def test_starts_ratio_computes_fraction_of_60_plus_appearances():
    rows = [{"minutes": 90}, {"minutes": 45}, {"minutes": 60}, {"minutes": 0}]
    assert minutes.starts_ratio(rows, window=4) == 0.5


def test_starts_ratio_respects_window():
    rows = [{"minutes": 0}] * 10 + [{"minutes": 90}] * 2
    assert minutes.starts_ratio(rows, window=2) == 1.0


def test_probabilities_from_starts_ratio_sum_to_one():
    p60, p_short, p_zero = minutes.probabilities_from_starts_ratio(0.8, 1.0)
    assert p60 == 0.8
    assert round(p60 + p_short + p_zero, 9) == 1.0


def test_probabilities_from_starts_ratio_scaled_by_availability():
    p60, _, _ = minutes.probabilities_from_starts_ratio(0.8, 0.5)
    assert p60 == 0.4


def test_expected_minutes():
    assert minutes.expected_minutes(p60=1.0, p_short=0.0) == 90
    assert minutes.expected_minutes(p60=0.0, p_short=1.0) == 30
    assert minutes.expected_minutes(p60=0.5, p_short=0.2) == 0.5 * 90 + 0.2 * 30
