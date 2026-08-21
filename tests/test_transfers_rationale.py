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
