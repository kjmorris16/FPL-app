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

## Testing

```bash
pytest
```

## Roadmap

- [x] Phase 1 — Data pipeline
- [x] Phase 2 — Scoring engine (expected points per player, 1/3/5 GW horizons)
- [ ] Phase 3 — Transfer optimizer
- [ ] Phase 4 — Chip planner (double/blank gameweeks, fixture swings)
- [ ] Phase 5 — Differential finder (mini-league-relative ownership)
- [ ] Phase 6 — Streamlit dashboard
- [ ] Phase 7 — Community sentiment cross-check (YouTube transcript ingestion)
