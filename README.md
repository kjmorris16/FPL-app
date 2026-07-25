# FPL App

A Python app to help win a Fantasy Premier League mini-league: transfer
recommendations driven by underlying stats (xG/xA/xGI), chip timing
planning, mini-league-specific differential finding, rival squad tracking,
and a community-sentiment cross-check layer — all viewable in a local
Streamlit dashboard.

Data comes from the official FPL public API (no auth required) and is
cached locally in SQLite so the app isn't hammering the API on every page
load.

## Project structure

```
fpl-app/
  data/                  # SQLite db lives here (gitignored)
  src/
    config.py            # shared paths + API URLs
    db.py                 # SQLite schema + connection helper
    ingest/               # API pull + refresh scripts
    scoring/              # expected points model
    transfers/            # transfer optimizer
    chips/                # chip timing planner
    differentials/        # mini-league ownership + differential finder
    dashboard/            # Streamlit app
  tests/
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Phase 1 — Data pipeline

Pulls `bootstrap-static` (players, teams, gameweeks) and `fixtures` from
the FPL API and stores them in SQLite (`data/fpl.db`). Optionally also
pulls per-player gameweek-by-gameweek history (`element-summary`) needed
for form/xG trend analysis in later phases.

Tables:
- `teams` — team strength ratings (overall/attack/defence, home/away)
- `events` — gameweeks (deadlines, current/next flags, finished state)
- `players` — current snapshot: price, ownership, form, season totals,
  xG/xA/xGI, ICT, status/injury flags
- `fixtures` — full season fixture list with FDR (fixture difficulty
  rating) per side
- `gameweek_stats` — per-player, per-gameweek actuals (only populated with
  `--with-history`, since it's one API request per player)

`gameweek_stats` and the `players` snapshot both include `saves` (needed for
Phase 2's goalkeeper save-points projection). If you already have a `data/fpl.db`
from before that column existed, `init_db()` migrates it automatically the
next time you run the refresh script or any scoring command.

Run it:

```bash
# quick refresh: players, teams, gameweeks, fixtures
python -m src.ingest.refresh

# slower, full refresh: also pulls per-player gameweek history
python -m src.ingest.refresh --with-history
```

Rerun the quick version each gameweek to pick up new prices, ownership,
form, and fixture results/difficulty. All inserts are upserts, so it's
always safe to rerun.

### A note on this environment

Outbound requests to `fantasy.premierleague.com` are blocked by this
Claude Code remote environment's network policy (proxy returns a 403 on
CONNECT). The ingestion code itself is fully unit-tested against mocked
API responses (`pytest`, all passing), but a live end-to-end pull hasn't
been run from inside this container. To actually populate `data/fpl.db`,
either:
- run `python -m src.ingest.refresh` locally (or in an environment whose
  network policy allows `fantasy.premierleague.com`), or
- adjust this environment's network policy to allow that host.

## Phase 2 — Scoring engine

Computes an expected-points (xPts) projection per player per gameweek, driven
by underlying stats rather than past points alone, and stores it in a new
`player_projections` table (`player_id, gameweek, projected_points, confidence,
computed_at`). The 1/3/5-gameweek horizon figures used by later phases are just
sums over consecutive rows in that table (`src/scoring/data_access.py:get_horizon_projection`).

Model inputs, per player per fixture:
- **Minutes probability** — probability of a 60+ minute appearance, from the
  last 6 gameweeks' start rate, scaled by an availability multiplier derived
  from `status` and `chance_of_playing_next_round` (`src/scoring/minutes.py`)
- **xG90 / xA90 / saves90** — blended 60/40 between a rolling 6-gameweek
  window and the season-long rate, so one big or bad game doesn't swing the
  projection too far (`src/scoring/underlying.py`)
- **Clean-sheet probability** — a Poisson model over expected goals conceded,
  built from FPL's own team attack/defence strength ratings, split by
  home/away (`src/scoring/clean_sheets.py`)
- **Fixture difficulty** — FPL's own 1-5 difficulty rating scales expected
  attacking output up/down, and inversely scales a goalkeeper's expected
  shots-faced/saves (`src/scoring/adjustments.py`)

Scoring follows FPL's actual points-per-action values, applied by position
(`src/scoring/constants.py`, combined in `src/scoring/points_model.py`):
goals (4/5/6 by position), assists (3, all positions), clean sheets (4 for
GK/DEF, 1 for MID, 0 for FWD), the -1-per-2-goals-conceded penalty (GK/DEF,
60+ mins only), and save points (1 per 3 saves, GK only, 60+ mins only via
minutes-weighting).

Edge cases handled:
- **New signings / promoted-team players** — below ~2 full games of history,
  a player's own rate stats are shrunk towards their position's league
  average (a simple shrinkage estimator: 0 minutes of history = pure
  position average, full history = pure individual rate) rather than left
  blank or zeroed out.
- **Rotation/injury risk** — projections scale with `expected_minutes`, not
  just the per-90 rate, so a nailed starter and a fringe player with the same
  underlying numbers get different point totals.
- **Double gameweeks** — a team with two fixture rows in the same gameweek
  gets its projection summed across both automatically (fixtures are matched
  per team per gameweek, so this falls out of the data model rather than
  needing special-cased logic).
- **Blank gameweeks** — no fixture that gameweek means `projected_points = 0`
  with `confidence = 1.0` (it's a certain zero, not a low-confidence guess).

**Confidence** (`src/scoring/confidence.py`) is based on how many minutes of
recent history back the projection: 0 minutes → a fixed low fallback (0.15);
6 full gameweeks (540 min) or more → 1.0; scales linearly in between. The CLI
buckets this into High/Medium/Low for display.

### Backtest

```bash
# requires gameweek_stats populated for the range being tested:
python -m src.ingest.refresh --with-history

python -m src.scoring.backtest --start-gw 1 --end-gw 10
```

For each gameweek in range, recomputes the projection using only data from
*before* that gameweek (no look-ahead — verified in
`tests/test_scoring_backtest.py`), compares it to the actual points scored,
and reports sample size, Pearson correlation, and mean absolute error (MAE)
across all (player, gameweek) pairs.

**This hasn't been run against real historical data yet** — same network
restriction as Phase 1 (see below). The backtest logic itself is unit-tested
against synthetic multi-gameweek data (correlation/MAE math, no-look-ahead
guarantee), but a real accuracy number requires a `data/fpl.db` with genuine
`gameweek_stats` history, which needs `--with-history` run somewhere with
network access to `fantasy.premierleague.com`.

### Quick check

```bash
python -m src.scoring.cli --recompute          # top 15 for the current/next GW
python -m src.scoring.cli --gw 5 --top 20
```

## Phase 3 — Transfer optimizer

Pulls your actual squad (manager ID `1213466` by default, see
`src/config.py:DEFAULT_MANAGER_ID`) from the FPL API each time it runs and
stores a snapshot (`my_manager_snapshot`: bank/squad value/free transfers;
`my_squad_history`: each of your 15 players, their purchase/sell price, and
captain/vice flags), so squad changes are tracked gameweek by gameweek. It
then ranks 0/1/2-transfer combinations by projected point gain over the next
1/3/5 gameweeks, using Phase 2's `player_projections`.

### Squad data (`src/ingest/manager.py`)

The public FPL API has no login-gated endpoint with exact sell prices, so
they're reconstructed:
- **Sell price** follows FPL's real rule -- keep half of any risen value
  (rounded down), eat the full loss if the price dropped -- computed from a
  player's most recent buy price found in `entry/{id}/transfers/`. A squad
  player who's never been re-bought this season (still your original
  gameweek-1 pick) has no purchase price in the public API; that case falls
  back to their current price (i.e. assumes zero banked profit), a
  conservative approximation that can only understate, never overstate,
  your available budget.
- **Free transfers** aren't returned directly either, so they're simulated
  forward from `entry/{id}/history/`'s per-gameweek transfer counts and
  costs (a transfer's cost is always a multiple of -4, so hits taken =
  cost / 4), skipping any gameweek a Wildcard or Free Hit was played (chip
  weeks don't touch the free-transfer counter). This is a best-effort
  reconstruction of the rollover-to-5 rule -- override it with
  `--free-transfers` if it ever drifts from what the FPL app shows you.

### Optimizer (`src/transfers/optimizer.py`)

- Only same-position replacements are considered (a documented
  simplification -- see the module docstring for why).
- Respects squad composition (2 GK / 5 DEF / 5 MID / 3 FWD is fixed by
  same-position swaps), the max-3-players-per-team rule, and budget (bank +
  sell price of whoever's being replaced).
- Evaluates 0, 1, and 2-transfer combinations. Two-transfer combos are built
  from each outgoing player's own shortlist of best replacements rather than
  an exhaustive pairwise search (`TOP_SINGLE_SWAPS_PER_PLAYER` in
  `constants.py`) -- fast, but can in theory miss a combo where pooling two
  sale prices unlocks an upgrade unaffordable alone.
- A hit-taking combo is only kept if its projected gain over the 5-gameweek
  decision horizon clears the -4-per-hit cost by a margin (1.5x, tunable via
  `HIT_MARGIN_MULTIPLIER`) -- a combo that merely breaks even on a hit isn't
  a real recommendation, so it's dropped rather than ranked low.

### Captain and rationale

The captain/vice-captain recommendation (`src/transfers/captain.py`) is
simply the two highest single-gameweek projected-points players in the
*resulting* squad (after the top transfer combo). The rationale
(`src/transfers/rationale.py`) is templated, not LLM-generated -- it's built
directly from the same gain and fixture-difficulty numbers the optimizer
already computed, which keeps it reproducible and testable.

### Weekly routine

```bash
python -m src.transfers.cli                     # pulls your squad, ranks transfers, prints captain pick
python -m src.transfers.cli --gw 12
python -m src.transfers.cli --free-transfers 2   # override the reconstructed FT count
python -m src.transfers.cli --no-refresh-squad   # reuse the last-pulled squad snapshot (no API call)
```

This has been verified end-to-end against a synthetic in-memory dataset
(correct budget/team-limit enforcement, correct hit-worthiness gating,
sensible captain/rationale output) but **not against your real squad** --
same network restriction as Phases 1-2: this sandbox can't reach
`fantasy.premierleague.com`, so pulling manager ID 1213466's actual squad
needs to happen from an environment with network access.

## Phase 4 — Chip timing planner

Recommends the best gameweeks to play Wildcard, Bench Boost, Triple
Captain, and Free Hit, based on fixture swings (double/blank gameweeks,
multi-gameweek runs of easy/hard opponents) rather than just current form.

### Chip status (`chip_usage` table)

`entry/{id}/history/`'s chip list is stored via `src/ingest/manager.py:fetch_chip_usage`
(also captured for free as part of `fetch_squad_snapshot`, which already
pulls that endpoint for the free-transfer simulation -- no extra API call).
Wildcard is handled as 2-per-season, 1-per-half (`src/chips/availability.py`);
Bench Boost, Triple Captain, and Free Hit are 1-per-season. The public API
doesn't expose the exact gameweek Wildcard resets for the second half, so the
halfway point (`WILDCARD_HALF_CUTOFF_GW`, default 19) is a documented
approximation, not something read from the API.

### Fixture swing detection (`src/chips/fixture_swings.py`)

Reuses Phase 2's `scoring.data_access.get_team_fixtures_map`, so DGW/BGW
detection and difficulty ratings stay consistent with the scoring model:
- **Double/blank gameweeks** -- a team with 2+ fixtures, or 0 fixtures, in a
  given gameweek.
- **Good/bad fixture runs** -- a 3+ gameweek stretch (tunable) where a team's
  average fixture difficulty is favourable (<= 2.4) or tough (>= 3.6).

### Chip value simulation (`src/chips/valuation.py`)

- **Bench Boost** -- summed projected points of your *current* squad
  snapshot's bench (squad positions 12-15) for each candidate gameweek.
- **Triple Captain** -- the marginal gain from tripling instead of doubling
  your best starting-XI captain option that week (exactly 1x their projected
  points, since normal captaincy already doubles). A DGW premium player's
  single-gameweek projection already includes both fixtures, so DGW weeks
  naturally score highest without special-casing.
- **Wildcard** -- not scored directly (it rebuilds the whole squad); instead
  a "window score" counts how many teams start a good fixture run, or have
  an upcoming double gameweek, right after each candidate week -- a high
  score means the player pool becomes a lot more attractive right after,
  which is exactly when rebuilding pays off.
- **Free Hit** -- counts how many of your own squad's players have no
  fixture in a candidate blank gameweek (falls back to a leaguewide blank
  count if no squad snapshot exists yet).

Bench Boost and Triple Captain assume your *current* bench/starting XI still
holds at the target gameweek -- a real squad will likely change via future
transfers, so values further out in the calendar are a rough guide, most
reliable near-term. Re-run closer to the target week for accuracy.

### Output

```bash
python -m src.chips.cli                    # top 3 candidate GWs per available chip
python -m src.chips.cli --horizon 15 --top 5
python -m src.chips.cli --full-calendar    # also print every GW's DGW/BGW notes
```

Recalculates from scratch each run (refetches chip usage, rescans the
current fixture list), so postponements or rescheduled DGWs are picked up
automatically next time it's run. Verified end-to-end against a synthetic
season with a planted DGW, a run of easy fixtures, and a blank gameweek: the
planner correctly picked the DGW week as the top Bench Boost/Triple Captain
window and the blank week as the top Free Hit window. Not yet run against
the real season's fixture list, for the same network reason as the phases
above.

## Phase 5 — Differential finder

Finds good players who are owned by few or none of the managers in *your
specific mini-league* -- FPL's global ownership % is close to useless for a
small private league; what matters is whether your actual rivals have a
player.

### League ID

`DEFAULT_LEAGUE_ID` in `src/config.py` is the single source of truth (currently
`103056`, a placeholder until the real league exists). Every module reads
from that one constant (or a `--league-id` CLI override) -- nothing else
hardcodes it. When the real league is created, change that one line.

### Data pull (`src/differentials/ingestion.py`)

- `fetch_league_managers` -- paginates through `leagues-classic/{id}/standings/`
  (handles leagues bigger than one results page) and stores every manager in
  `league_managers`. Raises a clear error pointing at `DEFAULT_LEAGUE_ID` if
  the league doesn't exist yet, rather than a bare 404 traceback.
- `fetch_league_picks` -- for every manager in the league, pulls their squad
  via the same picks-with-fallback logic Phase 3 uses for your own squad
  (now a public `manager.fetch_picks_with_fallback`, reused rather than
  duplicated), storing each pick in `league_manager_picks`
  (`manager_id, gameweek, player_id, is_captain`). A manager whose pull fails
  is skipped and logged, not fatal to the whole refresh.
- Rival chip usage reuses Phase 4's `chip_usage` table and
  `manager.fetch_chip_usage` directly -- it's already keyed by manager_id, so
  no new ingestion code was needed for that part.

### In-league ownership (`src/differentials/ownership.py`)

Ownership % and captaincy % per player, computed only from *this league's*
picks at the latest pulled gameweek. The denominator is the number of
managers actually pulled successfully that gameweek (not the league's
declared size), so one failed pull doesn't quietly skew every percentage.

### Differential ranking (`src/differentials/finder.py`)

`differential_score = projected_points * (1 - ownership_pct / 100)` -- a
simple linear inverse-ownership weighting (a great player owned by 0% of
the league scores its full projection; a great player owned by 100% scores
zero), not a sophisticated rivals-EV model, but transparent and easy to
reason about. Critically, the ranking runs over *every* player in the game,
not just players who appear in someone's picks -- a player nobody in the
league owns still needs to show up with ownership_pct=0, since that's
exactly the strongest kind of differential.

Three views, per the brief:
- `rank_differentials_to_transfer_in` -- best differentials not already in
  your squad.
- `rank_my_differentials` -- low-owned players you already own, so you know
  which of your picks are already paying off as differentials.
- `rank_high_owned` -- players owned by a lot of the league regardless of
  how well they're projecting, so you know your shared "safe pick" exposure
  even when it's underperforming.

### Output

```bash
python -m src.differentials.cli                        # full report for the configured league
python -m src.differentials.cli --league-id 12345       # override the league
python -m src.differentials.cli --top 10 --no-refresh
```

Prints the top differentials to transfer in (player, 1/3/5 GW projection,
in-league ownership %, in-league captaincy %), differentials you already
own, high-owned "safe" picks, and a rival chip-usage summary -- all
recomputed from scratch each run. Verified end-to-end against a synthetic
4-manager league (an unowned strong player correctly ranked as the top
differential, an already-owned low-ownership player surfaced separately, a
fully-owned player correctly flagged as shared exposure, and a rival's
already-used Wildcard correctly shown). Not yet run against a real mini-league,
for the same network reason as the phases above -- and this particular
league doesn't exist yet regardless.

## Phase 6 — Dashboard

A single Streamlit page tying together Phases 1-5, so a gameweek check is
"open the dashboard" instead of running five separate CLIs.

```bash
streamlit run src/dashboard/app.py
```

(`src/dashboard/app.py` inserts the project root onto `sys.path` at the top
of the file -- Streamlit otherwise runs scripts with only their own
directory on the path, which breaks `import src...` regardless of your
working directory when you launch it.)

Four tabs, each backed by the exact same modules the CLIs use (no logic
duplicated for the dashboard):
- **My Squad** -- bank/free transfers/squad value as metrics, and the 15-man
  squad as a table (position, team, price, next-GW projection, C/VC tags,
  and a per-player recent-form bar chart via `st.column_config.BarChartColumn`).
- **Transfer Recommendation** -- Phase 3's top combo (in/out, 1/3/5 GW gain,
  hit cost if any, remaining bank), its plain-English rationale, the
  resulting captain/vice-captain pick, and the next few alternatives.
- **Chip Timing** -- a status table (available/used, best gameweek, why) for
  all four chips, plus a bar chart of Bench Boost/Triple Captain value across
  the planning window and a list of upcoming DGW/BGW fixture swings.
- **Differentials** -- top candidates to transfer in and differentials
  already owned, side by side, using the configured league ID.

**Manual refresh** (`src/dashboard/refresh.py`, triggered by the sidebar
button): reruns Phase 1's ingestion, recomputes projections, refreshes your
squad and chip usage, and refreshes the configured league -- each step
wrapped independently so one failure (no network, or the placeholder league
not existing yet) doesn't block the others. All the reads elsewhere are
cached for a minute (`st.cache_data`) so clicking around the tabs doesn't
recompute transfer combos or differential rankings on every click; the
refresh button explicitly clears that cache afterwards.

Read-heavy `st.cache_data` functions are the norm here, but one non-obvious
Streamlit behavior was worth catching before shipping: `st.rerun()` right
after refreshing discards anything written earlier in that same script run,
so a naive `st.write(message)` before the rerun would never actually be
visible. The status messages are stashed in `st.session_state` and rendered
on the *next* run instead -- covered by
`tests/test_dashboard_app.py::test_refresh_button_status_messages_survive_the_rerun`.

**Verification**: an `AppTest`-based test (`tests/test_dashboard_app.py`)
confirms the app renders without raising against an empty database, with
every section showing a friendly "no data yet" message. Beyond that, since
this is a UI, I actually launched it (`streamlit run`) and drove it with a
headless browser (Playwright) against a synthetic dataset seeded under the
real manager ID (1213466) and the placeholder league ID (103056) -- covering
squad display (bank/FT/squad value, position table, recent-form bars,
captain/vice tags), a transfer recommendation with rationale and
captain/vice picks, the chip calendar (correctly flagging an already-used
Wildcard and surfacing a planted double-gameweek window), and both
differential views. I also clicked the refresh button against this
sandbox's blocked network and confirmed it fails each step gracefully
(readable warnings, no crash) rather than hanging or corrupting the
existing data -- this surfaced and fixed the `st.rerun()` message-loss bug
above. The synthetic data was removed afterward; nothing from this
verification is left in `data/fpl.db`. Screenshots from that session were
sent alongside this summary. Not yet checked against your real squad and
league, for the same network reason as every phase before it.

## Phase 8 — Pre-season squad selector

Live squad/picks data isn't available until GW1's deadline passes, so this
fills that gap: a full-squad recommendation built from last season's data
and whatever pre-season signal is reasonably available, rather than
current-season stats that don't exist yet. Phase 7 (community sentiment)
hasn't been built -- this phase's integration point for it is a documented
no-op until it exists (see below), per the brief's "if Phase 7 is built"
framing.

**Scope note**: the brief also asks for "squad changes -- new signings,
players who left, new manager appointments" as a secondary signal. The
public FPL API doesn't expose last season's team affiliation per player or
any manager/coaching data at all, so there's no reliable way to detect
"proven player moved to a new club" or "new manager" without fabricating
data. What *is* reliably derivable -- and is exactly the decision-relevant
part, per the brief's own scoring section -- is whether a player has *any*
top-flight history on record at all (rookie, promoted-team debut, first PL
season for an overseas signing), which drives the confidence flag below.
This boundary is deliberate, not an oversight.

### Last season's stats (`src/ingest/previous_season.py`)

Pulls `history_past` from `element-summary` for every current player (one
API call each, same slow pattern as Phase 1's `--with-history`) and stores
the most recent past-season entry in `player_previous_season_stats`. A
player with **no** `history_past` at all is simply not stored -- that
absence is itself the signal the confidence flag reads, rather than a
placeholder row.

```bash
python -m src.ingest.previous_season
```

Note this is a separate pull from the dashboard/CLI's live scoring run --
run it once (or whenever you want to refresh last-season data) before
using the pre-season selector; `src/preseason/scoring.py` reads whatever
was last stored, it doesn't trigger this ingestion itself.

### Scoring (`src/preseason/scoring.py`)

Reuses Phase 2's tested scoring machinery almost entirely -- the points
model, clean-sheet Poisson model, fixture-difficulty adjustments, and the
shrinkage estimator for new signings -- just fed last-season per-90 rates
instead of blended current-season ones, since `gameweek_stats` is
completely empty before GW1. The one real simplification: last season's
data is season totals, not per-gameweek rows, so there's a single
minutes-share factor (last-season minutes / a full 38-game season) rather
than Phase 2's fuller minutes-probability breakdown -- documented in the
module.

Friendly-appearance and creator-insight signals are small, additive nudges
layered on top afterward (a fixed +0.3 for a recorded goal/assist in a
friendly, a small confidence penalty for an established starter with zero
recorded pre-season minutes, +/-0.2 for creator buy/sell sentiment) --
never large enough to override the season-long signal that actually drives
the score. Both read from tables that don't exist yet in this codebase
(`friendly_appearances` -- the optional API-Football module was deliberately
not built this phase, since it needs your own API key to test against
meaningfully; `creator_insights` -- Phase 7) and degrade to a clean no-op
when the table is absent (`src/preseason/data_access.py`), rather than
erroring.

### Squad optimizer (`src/preseason/optimizer.py`)

Building a full 15 from ~700 candidates with no existing squad to start
from is a genuinely different problem from Phase 3's transfer optimizer
(which only ever evaluates small swaps against an existing squad via a
shortlisting heuristic). This uses a real mixed-integer linear program
(`pulp`, with its bundled CBC solver) to pick the true optimum under the
budget/position/team constraints, rather than a greedy approximation --
solves in well under a second for this problem size. Starting XI selection
enumerates FPL's valid (DEF, MID, FWD) formation shapes and picks the
highest-scoring one; captain/vice reuses Phase 3's exact "top two scorers"
rule.

### Output

```bash
python -m src.preseason.cli                    # suggested 15 + starting XI
python -m src.preseason.cli --budget 98.5 --horizon 3
```

The dashboard's fifth tab ("Pre-Season Squad") shows the same thing with a
clear banner: *"Based on last season's data and pre-season signal -- treat
as a starting point, not a certainty, until live data arrives after GW1."*
Squad grouped by position (price, score, confidence, next-3-gameweek
fixture difficulty per team, notes), an overall squad total-score metric
above the table, starting XI + formation, bench, and captain/vice. Fixture
difficulty (`src/preseason/data_access.py:get_team_fixture_ticker`) reuses
the same team-fixtures lookup the scoring engine itself relies on, so what's
displayed always matches what actually drove the score -- a double
gameweek shows both fixtures' difficulty joined with "/", a blank shows "-".

**"Must include" / "must exclude" player pickers** let you force specific
players in or out and have the ILP solver rebuild the rest of the squad
(and total score) around that constraint -- rather than a free-form edit of
the result table, which could easily produce an invalid squad (wrong
budget, too many from one team, wrong position counts) on its own. A
contradictory request (including and excluding the same player, or
excluding so many of one position that the quota can't be filled) surfaces
the same infeasibility error as a too-small budget.

Verified end-to-end against a synthetic 8-team league (correct budget/
position/team-cap enforcement in the ILP, correct formation and bench
ordering, confidence flags rendering correctly for no-history players) and
against a live browser session for the dashboard tab specifically. Not yet
run against the real 2026/27 pre-season data, for the same network reason
as every phase before it.

## Testing

```bash
pytest
```

## Roadmap

- [x] Phase 1 — Data pipeline
- [x] Phase 2 — Scoring engine (expected points per player, 1/3/5 GW horizons)
- [x] Phase 3 — Transfer optimizer
- [x] Phase 4 — Chip planner (double/blank gameweeks, fixture swings)
- [x] Phase 5 — Differential finder (mini-league-relative ownership)
- [x] Phase 6 — Streamlit dashboard
- [ ] Phase 7 — Community sentiment cross-check (YouTube transcript ingestion)
- [x] Phase 8 — Pre-season squad selector
