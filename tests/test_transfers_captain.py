from src.transfers import captain


def test_recommend_captain_picks_top_two_by_projection():
    projections = {1: 5.0, 2: 8.0, 3: 3.0, 4: 6.5}
    cap, vice = captain.recommend_captain([1, 2, 3, 4], projections)
    assert cap == 2
    assert vice == 4


def test_recommend_captain_ignores_players_without_a_projection():
    projections = {1: 5.0}
    cap, vice = captain.recommend_captain([1, 2], projections)
    assert cap == 1
    assert vice is None


def test_recommend_captain_empty_squad():
    cap, vice = captain.recommend_captain([], {})
    assert cap is None
    assert vice is None
