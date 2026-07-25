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

# How many top single-swap candidates (per outgoing player) to consider when
# building 2-transfer combos. Keeps the search tractable: rather than a full
# pairwise search over every possible replacement pair, we take each squad
# player's best valid single replacement and then look for the best *pair* of
# those across different outgoing players. This can miss a combo where
# pooling two players' budgets unlocks an upgrade unaffordable alone -- a
# documented simplification, not an exhaustive search.
TOP_SINGLE_SWAPS_PER_PLAYER = 3
