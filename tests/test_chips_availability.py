from src.chips import availability, constants as c


def test_wildcard_available_when_never_used():
    assert availability.wildcard_available([], current_gw=10)


def test_wildcard_unavailable_after_used_in_current_half():
    chip_usage = [{"chip_name": c.CHIP_WILDCARD, "event": 5}]
    assert not availability.wildcard_available(chip_usage, current_gw=10)  # both GW5 and GW10 are first half


def test_wildcard_available_in_second_half_after_first_half_used():
    chip_usage = [{"chip_name": c.CHIP_WILDCARD, "event": 5}]
    assert availability.wildcard_available(chip_usage, current_gw=25)  # second half, WC2 still open


def test_wildcard_unavailable_after_both_halves_used():
    chip_usage = [
        {"chip_name": c.CHIP_WILDCARD, "event": 5},
        {"chip_name": c.CHIP_WILDCARD, "event": 25},
    ]
    assert not availability.wildcard_available(chip_usage, current_gw=10)
    assert not availability.wildcard_available(chip_usage, current_gw=30)


def test_single_use_chip_available_when_unused():
    assert availability.single_use_chip_available([], c.CHIP_BENCH_BOOST)


def test_single_use_chip_unavailable_when_used():
    chip_usage = [{"chip_name": c.CHIP_BENCH_BOOST, "event": 15}]
    assert not availability.single_use_chip_available(chip_usage, c.CHIP_BENCH_BOOST)
    assert availability.single_use_chip_available(chip_usage, c.CHIP_FREE_HIT)


def test_get_available_chips_reports_all_four():
    chip_usage = [{"chip_name": c.CHIP_TRIPLE_CAPTAIN, "event": 12}]
    result = availability.get_available_chips(chip_usage, current_gw=15)
    assert result == {
        c.CHIP_WILDCARD: True,
        c.CHIP_FREE_HIT: True,
        c.CHIP_BENCH_BOOST: True,
        c.CHIP_TRIPLE_CAPTAIN: False,
    }
