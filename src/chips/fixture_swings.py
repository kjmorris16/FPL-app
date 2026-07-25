"""Scans the fixture list for double gameweeks, blank gameweeks, and
multi-gameweek stretches of favourable/unfavourable opponent difficulty.
Reuses `scoring.data_access.get_team_fixtures_map`, the same team-per-GW
fixture lookup Phase 2's projections engine relies on, so difficulty and
DGW/BGW detection stay consistent with the scoring model.
"""
from src.chips import constants as c
from src.scoring import data_access as scoring_data_access
from src.scoring.constants import FIXTURE_DIFFICULTY_NEUTRAL


def get_all_team_ids(conn) -> list[int]:
    return [row["id"] for row in conn.execute("SELECT id FROM teams")]


def detect_double_gameweeks(conn, start_gw: int, end_gw: int) -> dict[int, list[int]]:
    """gameweek -> team_ids playing 2+ times that gameweek."""
    fixtures_map = scoring_data_access.get_team_fixtures_map(conn, start_gw, end_gw)
    dgws: dict[int, list[int]] = {}
    for team_id, gw_fixtures in fixtures_map.items():
        for gw, fixtures in gw_fixtures.items():
            if len(fixtures) >= 2:
                dgws.setdefault(gw, []).append(team_id)
    return dgws


def detect_blank_gameweeks(conn, start_gw: int, end_gw: int) -> dict[int, list[int]]:
    """gameweek -> team_ids with no fixture that gameweek."""
    fixtures_map = scoring_data_access.get_team_fixtures_map(conn, start_gw, end_gw)
    all_teams = get_all_team_ids(conn)
    bgws: dict[int, list[int]] = {}
    for gw in range(start_gw, end_gw + 1):
        blanking = [team_id for team_id in all_teams if gw not in fixtures_map.get(team_id, {})]
        if blanking:
            bgws[gw] = blanking
    return bgws


def _team_run_average_difficulty(fixtures_map: dict, team_id: int, run_start_gw: int, window: int) -> float | None:
    """Average difficulty across a `window`-gameweek stretch. A blank
    gameweek within the window simply contributes no data point (it neither
    helps nor hurts the average) -- a documented simplification."""
    difficulties = []
    for gw in range(run_start_gw, run_start_gw + window):
        for fixture in fixtures_map.get(team_id, {}).get(gw, []):
            difficulties.append(fixture["difficulty"] or FIXTURE_DIFFICULTY_NEUTRAL)
    if not difficulties:
        return None
    return sum(difficulties) / len(difficulties)


def find_fixture_runs(conn, start_gw: int, end_gw: int, window: int = c.GOOD_RUN_MIN_LENGTH, good: bool = True) -> list[dict]:
    """Teams with a `window`-gameweek stretch of favourable (good=True) or
    unfavourable (good=False) fixtures, for every possible run start in
    [start_gw, end_gw - window + 1]. Returns a list of
    {team_id, run_start_gw, avg_difficulty}, most extreme first.
    """
    fixtures_map = scoring_data_access.get_team_fixtures_map(conn, start_gw, end_gw)
    all_teams = get_all_team_ids(conn)
    threshold = c.GOOD_FIXTURE_RUN_THRESHOLD if good else c.BAD_FIXTURE_RUN_THRESHOLD
    last_run_start = end_gw - window + 1

    runs = []
    for team_id in all_teams:
        for run_start in range(start_gw, last_run_start + 1):
            avg_difficulty = _team_run_average_difficulty(fixtures_map, team_id, run_start, window)
            if avg_difficulty is None:
                continue
            if (good and avg_difficulty <= threshold) or (not good and avg_difficulty >= threshold):
                runs.append({"team_id": team_id, "run_start_gw": run_start, "avg_difficulty": avg_difficulty})

    runs.sort(key=lambda r: r["avg_difficulty"], reverse=not good)
    return runs
