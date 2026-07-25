"""Estimates the expected value of playing each chip in a given gameweek.

Bench Boost and Triple Captain use the manager's *current* squad snapshot
projected forward to each candidate gameweek. This assumes the squad's bench
and starting XI composition at the snapshot gameweek still holds by the
target gameweek -- in reality it'll likely change via future transfers, so
values further out in the calendar are more of a rough guide than a firm
number. Re-run closer to the target week for accuracy.
"""
from src.chips import constants as c, fixture_swings
from src.transfers import data_access as transfers_data_access


def bench_boost_value(conn, manager_id: int, squad_gw: int, target_gw: int) -> float:
    """Projected points sitting on the bench (squad positions 12-15) of the
    manager's most recent squad snapshot, for `target_gw`."""
    squad = transfers_data_access.get_current_squad(conn, manager_id, squad_gw)
    bench_ids = [p["player_id"] for p in squad if p["squad_position"] in c.BENCH_POSITIONS]
    if not bench_ids:
        return 0.0
    totals = transfers_data_access.get_projection_totals(conn, bench_ids, start_gw=target_gw, horizons=(1,))
    return sum(totals[pid][1] for pid in bench_ids)


def triple_captain_value(conn, manager_id: int, squad_gw: int, target_gw: int) -> tuple[float, int | None]:
    """Marginal point gain from tripling (rather than doubling) your best
    captain option for `target_gw`: exactly one extra multiple of their
    projected points. Only the starting XI is considered -- captaining a
    bench player is never rational. Returns (gain, player_id), or (0.0, None)
    if the squad has no starters with a projection.
    """
    squad = transfers_data_access.get_current_squad(conn, manager_id, squad_gw)
    starter_ids = [p["player_id"] for p in squad if p["squad_position"] not in c.BENCH_POSITIONS]
    if not starter_ids:
        return 0.0, None
    totals = transfers_data_access.get_projection_totals(conn, starter_ids, start_gw=target_gw, horizons=(1,))
    best_id = max(starter_ids, key=lambda pid: totals[pid][1])
    return totals[best_id][1], best_id


def wildcard_window_score(conn, start_gw: int, end_gw: int, candidate_gw: int) -> tuple[int, set[int], set[int]]:
    """Higher score = a better week to Wildcard: teams starting a good
    fixture run right after this gameweek, plus teams with an upcoming double
    gameweek soon after. A high score means more of the player pool becomes
    attractive right after this week -- exactly when rebuilding pays off.
    Returns (score, teams_starting_good_run, teams_with_upcoming_dgw).
    """
    good_runs = fixture_swings.find_fixture_runs(conn, start_gw, end_gw, window=c.GOOD_RUN_MIN_LENGTH, good=True)
    teams_starting_good_run = {r["team_id"] for r in good_runs if r["run_start_gw"] == candidate_gw + 1}

    dgw_end = min(end_gw, candidate_gw + c.WILDCARD_DGW_LOOKAHEAD_GWS)
    dgws = fixture_swings.detect_double_gameweeks(conn, candidate_gw + 1, dgw_end) if dgw_end > candidate_gw else {}
    teams_with_upcoming_dgw = {team_id for teams in dgws.values() for team_id in teams}

    score = len(teams_starting_good_run) + len(teams_with_upcoming_dgw)
    return score, teams_starting_good_run, teams_with_upcoming_dgw


def free_hit_window_score(conn, manager_id: int, squad_gw: int, candidate_gw: int) -> int:
    """How many of the manager's own squad players have no fixture in
    `candidate_gw` -- the more of your XV blanks, the stronger the Free Hit
    case. Falls back to leaguewide blank severity (teams blanking) if no
    squad snapshot is available yet.
    """
    bgws = fixture_swings.detect_blank_gameweeks(conn, candidate_gw, candidate_gw)
    blanking_teams = set(bgws.get(candidate_gw, []))
    if not blanking_teams:
        return 0

    squad = transfers_data_access.get_current_squad(conn, manager_id, squad_gw) if squad_gw is not None else []
    if squad:
        return sum(1 for p in squad if p["team_id"] in blanking_teams)
    return len(blanking_teams)
