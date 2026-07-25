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

## Testing

```bash
pytest
```

## Roadmap

- [x] Phase 1 — Data pipeline
- [ ] Phase 2 — Scoring engine (expected points per player, 1/3/5 GW horizons)
- [ ] Phase 3 — Transfer optimizer
- [ ] Phase 4 — Chip planner (double/blank gameweeks, fixture swings)
- [ ] Phase 5 — Differential finder (mini-league-relative ownership)
- [ ] Phase 6 — Streamlit dashboard
- [ ] Phase 7 — Community sentiment cross-check (YouTube transcript ingestion)
