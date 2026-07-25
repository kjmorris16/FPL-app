"""Chip identifiers, season limits, and tunable constants for the chip planner."""

CHIP_WILDCARD = "wildcard"
CHIP_FREE_HIT = "freehit"
CHIP_BENCH_BOOST = "bboost"
CHIP_TRIPLE_CAPTAIN = "3xc"

CHIP_DISPLAY_NAMES = {
    CHIP_WILDCARD: "Wildcard",
    CHIP_FREE_HIT: "Free Hit",
    CHIP_BENCH_BOOST: "Bench Boost",
    CHIP_TRIPLE_CAPTAIN: "Triple Captain",
}

# Wildcard is 2-per-season, 1-per-half; every other chip here is 1-per-season.
# The public FPL API doesn't expose the exact gameweek Wildcard resets for the
# second half, so this is a documented approximation of the season's halfway
# point -- if it's off by a gameweek or two for a given season, override
# behaviour by adjusting this constant.
WILDCARD_HALF_CUTOFF_GW = 19

GOOD_FIXTURE_RUN_THRESHOLD = 2.4  # avg difficulty at/below this = a favourable run
BAD_FIXTURE_RUN_THRESHOLD = 3.6  # avg difficulty at/above this = a tough run
GOOD_RUN_MIN_LENGTH = 3  # gameweeks, per the "3+ gameweeks" requirement

PLANNING_HORIZON_GWS = 10  # how far ahead the chip calendar looks by default
BENCH_POSITIONS = (12, 13, 14, 15)  # FPL picks[].position: 1-11 starting XI, 12-15 bench

# How far past a candidate gameweek to look for an upcoming double gameweek
# when scoring how good a week that would be to play the Wildcard.
WILDCARD_DGW_LOOKAHEAD_GWS = 5
