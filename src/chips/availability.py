"""Determines which chips a manager still has available, from their chip
usage history. Wildcard needs special handling: it's usable twice a season,
once per half, so "available" depends on which half of the season we're
currently in.
"""
from src.chips import constants as c


def wildcard_available(chip_usage: list[dict], current_gw: int) -> bool:
    used_events = [row["event"] for row in chip_usage if row["chip_name"] == c.CHIP_WILDCARD]
    in_second_half = current_gw > c.WILDCARD_HALF_CUTOFF_GW
    half_already_used = any((event > c.WILDCARD_HALF_CUTOFF_GW) == in_second_half for event in used_events)
    return not half_already_used


def single_use_chip_available(chip_usage: list[dict], chip_name: str) -> bool:
    return not any(row["chip_name"] == chip_name for row in chip_usage)


def get_available_chips(chip_usage: list[dict], current_gw: int) -> dict[str, bool]:
    return {
        c.CHIP_WILDCARD: wildcard_available(chip_usage, current_gw),
        c.CHIP_FREE_HIT: single_use_chip_available(chip_usage, c.CHIP_FREE_HIT),
        c.CHIP_BENCH_BOOST: single_use_chip_available(chip_usage, c.CHIP_BENCH_BOOST),
        c.CHIP_TRIPLE_CAPTAIN: single_use_chip_available(chip_usage, c.CHIP_TRIPLE_CAPTAIN),
    }
