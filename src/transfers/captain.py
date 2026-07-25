"""Recommend a captain and vice-captain from a squad, based on highest
single-gameweek projected points."""


def recommend_captain(squad_player_ids: list[int], single_gw_projections: dict[int, float]) -> tuple[int | None, int | None]:
    """Returns (captain_id, vice_captain_id): the two highest single-GW
    projected-points players in the squad. Either may be None if fewer than
    1 or 2 squad players have a projection.
    """
    ranked = sorted(
        (pid for pid in squad_player_ids if pid in single_gw_projections),
        key=lambda pid: single_gw_projections[pid],
        reverse=True,
    )
    captain = ranked[0] if len(ranked) >= 1 else None
    vice = ranked[1] if len(ranked) >= 2 else None
    return captain, vice
