"""Shared paths and settings for the FPL app."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "fpl.db"

FPL_BASE_URL = "https://fantasy.premierleague.com/api"
BOOTSTRAP_STATIC_URL = f"{FPL_BASE_URL}/bootstrap-static/"
FIXTURES_URL = f"{FPL_BASE_URL}/fixtures/"


def element_summary_url(player_id: int) -> str:
    return f"{FPL_BASE_URL}/element-summary/{player_id}/"


def entry_picks_url(manager_id: int, gw: int) -> str:
    return f"{FPL_BASE_URL}/entry/{manager_id}/event/{gw}/picks/"


def entry_url(manager_id: int) -> str:
    return f"{FPL_BASE_URL}/entry/{manager_id}/"


def entry_history_url(manager_id: int) -> str:
    return f"{FPL_BASE_URL}/entry/{manager_id}/history/"


def entry_transfers_url(manager_id: int) -> str:
    return f"{FPL_BASE_URL}/entry/{manager_id}/transfers/"


def league_standings_url(league_id: int) -> str:
    return f"{FPL_BASE_URL}/leagues-classic/{league_id}/standings/"


# The user's own manager ID, so the Phase 3 weekly routine is a single command.
DEFAULT_MANAGER_ID = 1213466

DATA_DIR.mkdir(parents=True, exist_ok=True)
