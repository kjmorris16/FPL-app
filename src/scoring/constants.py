"""FPL scoring rules and tunable heuristic constants for the xPts model."""

GK, DEF, MID, FWD = 1, 2, 3, 4
POSITION_NAMES = {GK: "GK", DEF: "DEF", MID: "MID", FWD: "FWD"}
ALL_POSITIONS = (GK, DEF, MID, FWD)

# --- Official FPL points-per-action values ---
GOAL_POINTS = {GK: 6, DEF: 6, MID: 5, FWD: 4}
ASSIST_POINTS = 3
CLEAN_SHEET_POINTS = {GK: 4, DEF: 4, MID: 1, FWD: 0}
GOALS_CONCEDED_POINTS_PER_GOAL = -0.5  # -1 per 2 goals conceded, GK/DEF only, 60+ mins
SAVE_POINTS_PER_SAVE = 1 / 3  # 1 point per 3 saves, GK only
APPEARANCE_POINTS_60_PLUS = 2
APPEARANCE_POINTS_UNDER_60 = 1

CLEAN_SHEET_POSITIONS = {GK, DEF, MID}
GOALS_CONCEDED_POSITIONS = {GK, DEF}
SAVE_POSITIONS = {GK}

# --- Heuristic tuning constants (documented simplifying assumptions) ---
RECENT_WINDOW_GWS = 6
RECENT_FORM_WEIGHT = 0.6  # weight given to the recent window vs season-long rate

STATUS_UNAVAILABLE = {"i", "s", "u", "n"}
DOUBTFUL_STATUS = "d"
DEFAULT_DOUBTFUL_MULTIPLIER = 0.75

# Of the probability mass that isn't a 60+ minute appearance, the fraction that
# still gets some (sub/cameo) minutes, and the average length of that cameo.
SHORT_APPEARANCE_SHARE = 0.3
SHORT_APPEARANCE_AVG_MINUTES = 30

# Scale attacking output / defensive workload by fixture difficulty (1=easiest,
# 5=hardest), relative to a neutral midpoint of 3.
FIXTURE_DIFFICULTY_NEUTRAL = 3
FIXTURE_DIFFICULTY_SLOPE = 0.1

# Rough Premier League historical average goals scored by a team per game, used
# as the Poisson baseline for clean-sheet / goals-conceded estimation.
BASE_GOALS_PER_TEAM_PER_GAME = 1.4

# Below this much career minutes, shrink a player's individual rate stats
# towards their position's league average (new signings, promoted-team
# players, players just back from injury).
NEW_PLAYER_MINUTES_THRESHOLD = 180

# Minutes of recent history needed to call a projection "fully confident".
FULL_CONFIDENCE_MINUTES = RECENT_WINDOW_GWS * 90
FALLBACK_CONFIDENCE_NO_HISTORY = 0.15

CONFIDENCE_HIGH_THRESHOLD = 0.7
CONFIDENCE_MEDIUM_THRESHOLD = 0.35
