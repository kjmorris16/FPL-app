from src.scoring import underlying


def _row(minutes, expected_goals=0.0, expected_assists=0.0):
    return {"minutes": minutes, "expected_goals": expected_goals, "expected_assists": expected_assists}


def test_per90_basic():
    rows = [_row(90, expected_goals=0.9), _row(90, expected_goals=0.45)]
    assert underlying.per90(rows, "expected_goals") == 0.675


def test_per90_handles_zero_minutes():
    rows = [_row(0, expected_goals=0.5)]
    assert underlying.per90(rows, "expected_goals") == 0.0


def test_per90_handles_missing_none_values():
    rows = [{"minutes": 90, "expected_goals": None}]
    assert underlying.per90(rows, "expected_goals") == 0.0


def test_blended_per90_returns_none_for_no_history():
    assert underlying.blended_per90([], "expected_goals") is None


def test_blended_per90_weights_recent_window_more_heavily():
    # Season-long rate is low (0.1/90), but the most recent 6 games are much
    # hotter (0.9/90) -- the blend should sit between the two, closer to recent.
    old_rows = [_row(90, expected_goals=0.1) for _ in range(10)]
    recent_rows = [_row(90, expected_goals=0.9) for _ in range(6)]
    history = old_rows + recent_rows

    blended = underlying.blended_per90(history, "expected_goals", recent_window=6, recent_weight=0.6)

    season_rate = underlying.per90(history, "expected_goals")
    recent_rate = underlying.per90(recent_rows, "expected_goals")
    assert season_rate < blended < recent_rate
    assert blended == 0.6 * recent_rate + 0.4 * season_rate


def test_total_minutes():
    rows = [_row(90), _row(45), _row(0)]
    assert underlying.total_minutes(rows) == 135


def test_shrink_to_position_average_full_weight_for_established_player():
    result = underlying.shrink_to_position_average(
        individual_rate=0.5, minutes_played=1000, position_avg_rate=0.2, full_confidence_minutes=180
    )
    assert result == 0.5


def test_shrink_to_position_average_pure_fallback_for_zero_minutes():
    result = underlying.shrink_to_position_average(
        individual_rate=None, minutes_played=0, position_avg_rate=0.2, full_confidence_minutes=180
    )
    assert result == 0.2


def test_shrink_to_position_average_blends_partial_history():
    result = underlying.shrink_to_position_average(
        individual_rate=0.4, minutes_played=90, position_avg_rate=0.2, full_confidence_minutes=180
    )
    # 90/180 = 0.5 weight on the individual rate
    assert result == 0.5 * 0.4 + 0.5 * 0.2
