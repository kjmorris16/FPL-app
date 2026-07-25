"""Thin wrapper around the official FPL public API with retries."""
import logging
import time

import requests

from src.config import (
    BOOTSTRAP_STATIC_URL,
    FIXTURES_URL,
    element_summary_url,
    entry_history_url,
    entry_picks_url,
    entry_transfers_url,
    entry_url,
    league_standings_url,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
MAX_RETRIES = 3
BACKOFF_SECONDS = 2


def _get_json(url: str) -> dict:
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logger.warning("Request failed (attempt %d/%d) for %s: %s", attempt, MAX_RETRIES, url, exc)
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} attempts") from last_error


def get_bootstrap_static() -> dict:
    """Players, teams, gameweeks (events), and current ownership/form snapshot."""
    return _get_json(BOOTSTRAP_STATIC_URL)


def get_fixtures() -> list[dict]:
    """Full season fixture list with difficulty ratings."""
    return _get_json(FIXTURES_URL)


def get_element_summary(player_id: int) -> dict:
    """Per-player gameweek history and underlying stats."""
    return _get_json(element_summary_url(player_id))


def get_entry_picks(manager_id: int, gw: int) -> dict:
    """A specific manager's squad for a given gameweek."""
    return _get_json(entry_picks_url(manager_id, gw))


def get_league_standings(league_id: int, page: int = 1) -> dict:
    """A page of a mini-league's classic standings (manager IDs, names, ranks)."""
    return _get_json(league_standings_url(league_id, page))


def get_entry(manager_id: int) -> dict:
    """A manager's public profile (team name, current gameweek, etc.)."""
    return _get_json(entry_url(manager_id))


def get_entry_history(manager_id: int) -> dict:
    """A manager's gameweek-by-gameweek history this season, plus chip usage."""
    return _get_json(entry_history_url(manager_id))


def get_entry_transfers(manager_id: int) -> list[dict]:
    """A manager's full transfer history this season (element in/out and prices paid)."""
    return _get_json(entry_transfers_url(manager_id))
