"""Squad rules and tunable constants for the transfer optimizer."""
from src.scoring.constants import DEF, FWD, GK, MID  # re-exported for convenience

SQUAD_COMPOSITION = {GK: 2, DEF: 5, MID: 5, FWD: 3}
MAX_PLAYERS_PER_TEAM = 3

HIT_COST = 4  # points deducted per transfer beyond your free transfers
MAX_PAID_HITS_CONSIDERED = 1  # i.e. evaluate 0, 1, or 2 total transfers

# A hit-taking combo is only worth recommending if its projected gain over the
# hit-decision horizon clearly clears the points cost -- not just barely.
HIT_DECISION_HORIZON_GWS = 5
HIT_MARGIN_MULTIPLIER = 1.5  # gain must be >= 1.5x the hit cost to be "worth it"

DEFAULT_RANKING_HORIZON_GWS = 5
REPORTED_HORIZONS_GWS = (1, 3, 5)

# --- Weak-link scoring (Part 1: `src/transfers/weakness.py`) ---
# Configurable weights for `weakness.compute_weakness_score` -- kept as named
# constants, not inline literals, so they can be tuned once there's a few
# real gameweeks of results to compare the ranking against.
WEAKNESS_REPLACEMENT_GAP_WEIGHT = 0.5
WEAKNESS_FORM_DECLINE_WEIGHT = 0.25
WEAKNESS_FIXTURE_SWING_WEIGHT = 0.15
WEAKNESS_MINUTES_RISK_WEIGHT = 0.1

WEAKNESS_HORIZON_GWS = 5  # "3-5 gameweek projection" -- the fuller end, matching HIT_DECISION_HORIZON_GWS below
PRICE_BAND_TENTHS = 10  # "similar price band" for the replacement_gap comparison -- +/- £1.0m
FORM_DECLINE_WINDOW_GWS = 6  # "last 4-6 games" for the form-decline modifier

# How much higher a same-position teammate's recent starts_ratio must be
# than this player's own before it counts as a real rotation/new-signing
# threat rather than ordinary week-to-week squad rotation noise.
MINUTES_RISK_TEAMMATE_OVERTAKE_MARGIN = 0.25

# If the single weakest player has no replacement worth making, how many
# further players down the weakness ranking to try before giving up.
WEAK_LINK_CANDIDATES_TO_TRY = 3

# How many top single-swap candidates (per outgoing player) to consider when
# building 2-transfer combos. Keeps the search tractable: rather than a full
# pairwise search over every possible replacement pair, we take each squad
# player's best valid single replacement and then look for the best *pair* of
# those across different outgoing players. This can miss a combo where
# pooling two players' budgets unlocks an upgrade unaffordable alone -- a
# documented simplification, not an exhaustive search.
TOP_SINGLE_SWAPS_PER_PLAYER = 3
