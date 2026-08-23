from src.transfers import rationale
from src.transfers.optimizer import SwapCandidate, TransferCombo


def _combo(swaps, hit_cost=0):
    horizon = 5
    gains = {horizon: sum(s.gains[horizon] for s in swaps)}
    net_gains = {horizon: gains[horizon] - hit_cost}
    return TransferCombo(swaps=swaps, gains=gains, hit_cost=hit_cost, net_gains=net_gains, remaining_bank=0, worth_the_hit=True)


def test_build_rationale_no_transfers():
    combo = _combo([])
    text = rationale.build_rationale(combo, {})
    assert "no transfer" in text.lower()


def test_build_rationale_single_free_swap_mentions_players_and_gain():
    swap = SwapCandidate(
        out_player={"web_name": "Oldman", "player_id": 1},
        in_player={"web_name": "Newman", "player_id": 2},
        cost_delta=5,
        gains={5: 8.5},
    )
    combo = _combo([swap], hit_cost=0)
    text = rationale.build_rationale(combo, {2: 2.0})

    assert "Newman" in text
    assert "Oldman" in text
    assert "+8.5" in text
    assert "favourable" in text
    assert "hit" not in text.lower()


def test_build_rationale_mentions_hit_cost_when_applicable():
    swap = SwapCandidate(
        out_player={"web_name": "Oldman", "player_id": 1},
        in_player={"web_name": "Newman", "player_id": 2},
        cost_delta=5,
        gains={5: 9.0},
    )
    combo = _combo([swap], hit_cost=4)
    text = rationale.build_rationale(combo, {2: 4.0})

    assert "-4 hit" in text
    assert "5.0" in text  # net gain (9 - 4)


def test_describe_fixture_run_buckets():
    assert "favourable" in rationale.describe_fixture_run(2.0)
    assert "middling" in rationale.describe_fixture_run(3.0)
    assert "tough" in rationale.describe_fixture_run(4.5)
    assert rationale.describe_fixture_run(None) is None


def test_build_captain_rationale_mentions_points_and_fixture():
    text = rationale.build_captain_rationale("Salah", 9.2, fixture_difficulty=2.0)
    assert "9.2" in text
    assert "favourable" in text
    assert "form" in text.lower()


def test_build_captain_rationale_handles_no_fixture_difficulty():
    text = rationale.build_captain_rationale("Salah", 9.2, fixture_difficulty=None)
    assert "9.2" in text
    assert text.endswith(".")


def test_build_weak_link_flagged_reason_names_the_dominant_modifier():
    text = rationale.build_weak_link_flagged_reason("Oldman", "form_decline")
    assert text.startswith("Oldman is this week's weak link:")
    assert "xG + xA per 90" in text


def test_build_weak_link_flagged_reason_covers_every_reason_key():
    for reason_key in ("replacement_gap", "form_decline", "fixture_swing", "minutes_risk"):
        text = rationale.build_weak_link_flagged_reason("Oldman", reason_key)
        assert text.startswith("Oldman is this week's weak link:")
        assert text.endswith(".")


def test_build_weak_link_replacement_reason_mentions_price_and_gain():
    text = rationale.build_weak_link_replacement_reason(
        "Oldman", {"web_name": "Newman", "now_cost": 75}, net_gain=3.5, horizon=5,
    )
    assert "Newman" in text
    assert "£7.5m" in text
    assert "+3.5" in text
    assert "Oldman" in text


def test_build_weak_link_replacement_reason_includes_fixture_and_hit_cost():
    text = rationale.build_weak_link_replacement_reason(
        "Oldman", {"web_name": "Newman", "now_cost": 75}, net_gain=8.0, horizon=5,
        fixture_difficulty=2.0, hit_cost=4,
    )
    assert "favourable" in text
    assert "-4 hit cost" in text


def test_build_weak_link_replacement_reason_no_fixture_data_omits_clause():
    text = rationale.build_weak_link_replacement_reason(
        "Oldman", {"web_name": "Newman", "now_cost": 75}, net_gain=3.5, horizon=5,
    )
    assert "helped by" not in text
