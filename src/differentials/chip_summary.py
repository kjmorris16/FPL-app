"""Rival chip usage summary -- reuses Phase 4's chip_usage table and
ingestion directly, since it's already keyed by manager_id and works for any
manager, not just the user.
"""
import logging

from src.chips import availability
from src.differentials import data_access
from src.ingest import manager as manager_ingest

logger = logging.getLogger(__name__)


def fetch_rival_chip_usage(conn, league_id: int, current_gw: int, refresh: bool = True) -> dict[int, dict]:
    """manager_id -> {chips_used, available, manager_name, team_name}."""
    managers = data_access.get_league_managers(conn, league_id)
    summary = {}
    for m in managers:
        manager_id = m["manager_id"]
        if refresh:
            try:
                manager_ingest.fetch_chip_usage(conn, manager_id)
            except RuntimeError as exc:
                logger.warning("Couldn't refresh chip usage for manager %d: %s", manager_id, exc)

        chip_usage = [
            dict(row) for row in conn.execute(
                "SELECT chip_name, event FROM chip_usage WHERE manager_id = ?", (manager_id,)
            )
        ]
        summary[manager_id] = {
            "chips_used": chip_usage,
            "available": availability.get_available_chips(chip_usage, current_gw),
            "manager_name": m.get("manager_name"),
            "team_name": m.get("team_name"),
        }
    return summary
