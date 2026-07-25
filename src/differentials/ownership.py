"""Computes in-league ownership and captaincy percentages -- how many of
*this specific mini-league's* managers own or captain each player, as
opposed to FPL's site-wide ownership %, which tells you almost nothing
useful in a small private league.
"""
from src.differentials import data_access


def compute_ownership(conn, league_id: int, gw: int) -> dict[int, dict]:
    """player_id -> {owned_by, ownership_pct, captained_by, captaincy_pct}.

    The denominator is the number of managers we actually have pick data for
    at this gameweek, not the league's declared size -- so a manager whose
    pick pull failed doesn't silently skew every percentage.
    """
    picks = data_access.get_league_picks(conn, league_id, gw)
    manager_ids = {p["manager_id"] for p in picks}
    total_managers = len(manager_ids)
    if total_managers == 0:
        return {}

    owned_by: dict[int, set] = {}
    captained_by: dict[int, set] = {}
    for pick in picks:
        owned_by.setdefault(pick["player_id"], set()).add(pick["manager_id"])
        if pick["is_captain"]:
            captained_by.setdefault(pick["player_id"], set()).add(pick["manager_id"])

    result = {}
    for player_id, managers in owned_by.items():
        cap_managers = captained_by.get(player_id, set())
        result[player_id] = {
            "owned_by": len(managers),
            "ownership_pct": round(len(managers) / total_managers * 100, 1),
            "captained_by": len(cap_managers),
            "captaincy_pct": round(len(cap_managers) / total_managers * 100, 1),
        }
    return result
