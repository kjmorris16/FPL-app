"""Constants for Phase 8's pre-season squad selector.

Reuses Phase 2's scoring machinery (points_model, clean_sheets, adjustments,
underlying's shrinkage estimator, confidence scoring) fed with last-season
rates instead of blended current-season ones, since gameweek_stats is
entirely empty before GW1.
"""
from src.scoring.constants import DEF, FWD, GK, MID  # re-exported for convenience

DEFAULT_BUDGET_TENTHS = 1000  # FPL's well-established standard: a £100.0m starting squad budget
SQUAD_COMPOSITION = {GK: 2, DEF: 5, MID: 5, FWD: 3}
MAX_PLAYERS_PER_TEAM = 3

START_GW = 1

# Kept as a single constant on purpose: scoring projects across exactly the
# gameweeks the dashboard's fixture-difficulty ticker displays, no more --
# projecting further than what's shown would let fixtures the user can't
# see quietly move the score, making the visible ticker not actually
# explain it.
FIXTURE_HORIZON_GWS = 3  # "opening 3-5 gameweek difficulty" per the brief
FIXTURE_TICKER_GWS = FIXTURE_HORIZON_GWS

# A full Premier League season's minutes (38 games), used as the denominator
# for a player's last-season minutes-share.
FULL_SEASON_MINUTES = 38 * 90

# Below this many last-season minutes, a player's own rate stats are shrunk
# towards their position's league average (same shrinkage estimator as
# Phase 2, just with a season-long threshold instead of a 6-gameweek one).
SHRINKAGE_FULL_WEIGHT_MINUTES = 1500

# Minutes of last-season evidence needed to call a pre-season projection
# "fully confident". A whole season's minutes is a much stronger prior than
# Phase 2's 6-recent-gameweeks window, hence the higher bar.
FULL_CONFIDENCE_MINUTES = 2500
FALLBACK_CONFIDENCE_NO_HISTORY = 0.15

# Valid FPL starting-XI shapes: (DEF, MID, FWD) triples that sum to 10 outfield
# starters, honoring FPL's own minimums (>=3 DEF, >=2 MID, >=1 FWD). The GK
# slot is always exactly 1 and handled separately.
VALID_FORMATIONS = [(d, m, f) for d in range(3, 6) for m in range(2, 6) for f in range(1, 4) if d + m + f == 10]

# Secondary, deliberately small signals -- never meant to move the primary
# last-season-driven score by much.
FRIENDLY_APPEARANCE_BONUS = 0.3
NAILED_LAST_SEASON_MINUTES = 2500  # "established starter" bar for the zero-preseason-minutes flag
CREATOR_SENTIMENT_NUDGE = 0.2

NO_HISTORY_NOTE = "No top-flight history on record -- rookie, promoted-team debut, or first PL season for an overseas signing."
