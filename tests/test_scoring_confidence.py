from src.scoring import confidence, constants as c


def test_confidence_score_zero_minutes_uses_fallback():
    assert confidence.confidence_score(0) == c.FALLBACK_CONFIDENCE_NO_HISTORY


def test_confidence_score_full_minutes_caps_at_one():
    assert confidence.confidence_score(c.FULL_CONFIDENCE_MINUTES * 2) == 1.0


def test_confidence_score_partial_minutes_scales_linearly():
    half = c.FULL_CONFIDENCE_MINUTES / 2
    assert confidence.confidence_score(half) == 0.5


def test_horizon_confidence_averages():
    assert confidence.horizon_confidence([1.0, 0.5, 0.0]) == 0.5


def test_horizon_confidence_empty_is_zero():
    assert confidence.horizon_confidence([]) == 0.0


def test_confidence_label_buckets():
    assert confidence.confidence_label(0.9) == "High"
    assert confidence.confidence_label(0.5) == "Medium"
    assert confidence.confidence_label(0.1) == "Low"
