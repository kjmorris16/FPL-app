"""Pulls a mini-league's manager list and each rival's current squad from the
FPL API, so in-league ownership can be computed -- as opposed to FPL's
global ownership %, which is close to useless for a small private league.
"""
import logging
from datetime import datetime, timezone

from src.ingest import api_client
from src.ingest import manager as manager_ingest
from src.scoring import data_access as scoring_data_access

logger = logging.getLogger(__name__)


def fetch_league_managers(conn, league_id: int) -> list[dict]:
    """Pulls every manager in the league (paginated) and stores them in
    `league_managers`. Raises a clear error if the league doesn't exist yet --
    e.g. the placeholder league ID hasn't been created."""
    managers = []
    page = 1
    while True:
        try:
            payload = api_client.get_league_standings(league_id, page=page)
        except RuntimeError as exc:
            raise RuntimeError(
                f"Couldn't fetch mini-league {league_id}. If this is still the placeholder ID, "
                "update DEFAULT_LEAGUE_ID in src/config.py once your real league exists."
            ) from exc

        standings = payload.get("standings", {})
        managers.extend(standings.get("results", []))
        if not standings.get("has_next"):
            break
        page += 1

    pulled_at = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """
        INSERT INTO league_managers (league_id, manager_id, manager_name, team_name, rank, total_points, pulled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(league_id, manager_id) DO UPDATE SET
            manager_name=excluded.manager_name, team_name=excluded.team_name,
            rank=excluded.rank, total_points=excluded.total_points, pulled_at=excluded.pulled_at
        """,
        [
            (league_id, m["entry"], m.get("player_name"), m.get("entry_name"), m.get("rank"), m.get("total"), pulled_at)
            for m in managers
        ],
    )
    logger.info("Stored %d managers for league %d", len(managers), league_id)
    return managers


def fetch_league_picks(conn, league_id: int, gw: int | None = None) -> int:
    """For every manager in the league, pull their current squad (reusing the
    same picks-with-fallback logic Phase 3 uses for the user's own squad) and
    store it in `league_manager_picks`. Returns the number of managers
    successfully pulled.
    """
    if gw is None:
        gw = scoring_data_access.get_current_gw(conn)

    managers = [dict(row) for row in conn.execute(
        "SELECT manager_id FROM league_managers WHERE league_id = ?", (league_id,)
    )]
    if not managers:
        managers = [{"manager_id": m["entry"]} for m in fetch_league_managers(conn, league_id)]

    pulled_at = datetime.now(timezone.utc).isoformat()
    success_count = 0
    for m in managers:
        manager_id = m["manager_id"]
        try:
            _picks_gw, payload = manager_ingest.fetch_picks_with_fallback(manager_id, gw)
        except RuntimeError as exc:
            logger.warning("Skipping manager %d in league %d: %s", manager_id, league_id, exc)
            continue

        rows = [
            (league_id, manager_id, gw, pick["element"], int(bool(pick.get("is_captain"))), pulled_at)
            for pick in payload.get("picks", [])
        ]
        if rows:
            conn.executemany(
                """
                INSERT INTO league_manager_picks (league_id, manager_id, gw, player_id, is_captain, pulled_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(league_id, manager_id, gw, player_id) DO UPDATE SET
                    is_captain=excluded.is_captain, pulled_at=excluded.pulled_at
                """,
                rows,
            )
            success_count += 1

    logger.info("Stored picks for %d/%d managers in league %d, GW%d", success_count, len(managers), league_id, gw)
    return success_count
