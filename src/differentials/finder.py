"""Ranks differential candidates: players who project well but are owned by
few (or none) of this mini-league's managers -- the whole point of a
differential is that your rivals don't have them.
"""
from src.differentials import ownership as ownership_module
from src.transfers import data_access as transfers_data_access

REPORTED_HORIZONS_GWS = (1, 3, 5)
RANKING_HORIZON_GWS = 5

_EMPTY_OWNERSHIP = {"owned_by": 0, "ownership_pct": 0.0, "captained_by": 0, "captaincy_pct": 0.0}


def differential_score(projected_points: float, ownership_pct: float) -> float:
    """A great player owned by 0% of the league is a stronger differential
    than a decent player owned by 20% of it -- a simple linear
    inverse-ownership weighting, not a sophisticated rivals-EV model."""
    return projected_points * (1 - ownership_pct / 100)


def build_differential_table(
    conn,
    league_id: int,
    league_gw: int,
    start_gw: int,
    horizons: tuple = REPORTED_HORIZONS_GWS,
    max_ownership_pct: float = 100.0,
) -> list[dict]:
    """Every player in the game, combined with their in-league ownership
    (defaulting to 0% for anyone nobody in the league owns -- these are
    exactly the strongest potential differentials, so they must not be
    dropped just because they're absent from any manager's picks) and their
    projected points. `max_ownership_pct` filters out anyone above that
    ownership (100 = no filtering).
    """
    league_ownership = ownership_module.compute_ownership(conn, league_id, league_gw)
    player_ids = [p["player_id"] for p in transfers_data_access.get_candidate_pool(conn)]
    proj_totals = transfers_data_access.get_projection_totals(conn, player_ids, start_gw, horizons)

    rows = []
    for player_id in player_ids:
        own = league_ownership.get(player_id, _EMPTY_OWNERSHIP)
        if own["ownership_pct"] > max_ownership_pct:
            continue
        gains = proj_totals.get(player_id, {h: 0.0 for h in horizons})
        rows.append(
            {
                "player_id": player_id,
                "projected_points": gains,
                "ownership_pct": own["ownership_pct"],
                "captaincy_pct": own["captaincy_pct"],
                "owned_by": own["owned_by"],
                "captained_by": own["captained_by"],
                "differential_score": differential_score(gains.get(RANKING_HORIZON_GWS, 0.0), own["ownership_pct"]),
            }
        )
    return rows


def rank_differentials_to_transfer_in(
    conn, league_id: int, my_manager_id: int, league_gw: int, my_squad_gw: int | None, start_gw: int,
    top_n: int = 20, max_ownership_pct: float = 30.0,
) -> list[dict]:
    """Differentials worth transferring in: not already in my squad."""
    my_squad_ids = _my_squad_ids(conn, my_manager_id, my_squad_gw)
    table = build_differential_table(conn, league_id, league_gw, start_gw, max_ownership_pct=max_ownership_pct)
    candidates = [row for row in table if row["player_id"] not in my_squad_ids]
    candidates.sort(key=lambda r: r["differential_score"], reverse=True)
    return candidates[:top_n]


def rank_my_differentials(
    conn, league_id: int, my_manager_id: int, league_gw: int, my_squad_gw: int | None, start_gw: int,
    top_n: int = 20, max_ownership_pct: float = 30.0,
) -> list[dict]:
    """Differentials I already own: low-owned-in-league players already in my
    squad, so I know which of my picks are already working in my favor."""
    my_squad_ids = _my_squad_ids(conn, my_manager_id, my_squad_gw)
    table = build_differential_table(conn, league_id, league_gw, start_gw, max_ownership_pct=max_ownership_pct)
    candidates = [row for row in table if row["player_id"] in my_squad_ids]
    candidates.sort(key=lambda r: r["differential_score"], reverse=True)
    return candidates[:top_n]


def rank_high_owned(
    conn, league_id: int, league_gw: int, start_gw: int, min_ownership_pct: float = 50.0, top_n: int = 20,
) -> list[dict]:
    """Players owned by a lot of the league regardless of how well they
    project -- your "safe" shared exposure, useful to flag even if they're
    underperforming."""
    table = build_differential_table(conn, league_id, league_gw, start_gw, max_ownership_pct=100.0)
    candidates = [row for row in table if row["ownership_pct"] >= min_ownership_pct]
    candidates.sort(key=lambda r: r["ownership_pct"], reverse=True)
    return candidates[:top_n]


def _my_squad_ids(conn, my_manager_id: int, my_squad_gw: int | None) -> set:
    if my_squad_gw is None:
        return set()
    return {p["player_id"] for p in transfers_data_access.get_current_squad(conn, my_manager_id, my_squad_gw)}
