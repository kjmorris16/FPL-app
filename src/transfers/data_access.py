"""Read helpers for the transfer optimizer. Keeps SQL out of the model code."""
import sqlite3


def get_latest_squad_gw(conn: sqlite3.Connection, manager_id: int) -> int | None:
    row = conn.execute(
        "SELECT MAX(gw) AS gw FROM my_squad_history WHERE manager_id = ?", (manager_id,)
    ).fetchone()
    return row["gw"] if row and row["gw"] is not None else None


def get_manager_snapshot(conn: sqlite3.Connection, manager_id: int, gw: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM my_manager_snapshot WHERE manager_id = ? AND gw = ?", (manager_id, gw)
    ).fetchone()
    return dict(row) if row else None


def get_current_squad(conn: sqlite3.Connection, manager_id: int, gw: int) -> list[dict]:
    """The manager's 15-man squad at the given snapshot gameweek, joined with
    each player's current position/team/price so the optimizer doesn't need
    a second round trip.
    """
    rows = conn.execute(
        """
        SELECT h.player_id, h.squad_position, h.is_captain, h.is_vice_captain,
               h.multiplier, h.purchase_price, h.sell_price,
               p.web_name, p.element_type, p.team_id, p.now_cost, p.status,
               p.chance_of_playing_next_round
        FROM my_squad_history h
        JOIN players p ON p.id = h.player_id
        WHERE h.manager_id = ? AND h.gw = ?
        ORDER BY h.squad_position
        """,
        (manager_id, gw),
    ).fetchall()
    return [dict(row) for row in rows]


def get_candidate_pool(conn: sqlite3.Connection) -> list[dict]:
    """Every player, with the fields the optimizer needs to evaluate a swap."""
    rows = conn.execute(
        "SELECT id AS player_id, web_name, element_type, team_id, now_cost, status, "
        "chance_of_playing_next_round FROM players"
    ).fetchall()
    return [dict(row) for row in rows]


def get_projection_totals(conn: sqlite3.Connection, player_ids: list[int], start_gw: int, horizons: tuple[int, ...]) -> dict[int, dict[int, float]]:
    """player_id -> {horizon: summed_projected_points}, for each horizon in `horizons`."""
    if not player_ids:
        return {}
    max_horizon = max(horizons)
    placeholders = ",".join("?" for _ in player_ids)
    rows = conn.execute(
        f"""
        SELECT player_id, gameweek, projected_points FROM player_projections
        WHERE player_id IN ({placeholders}) AND gameweek BETWEEN ? AND ?
        """,
        (*player_ids, start_gw, start_gw + max_horizon - 1),
    ).fetchall()

    by_player_gw: dict[int, dict[int, float]] = {}
    for row in rows:
        by_player_gw.setdefault(row["player_id"], {})[row["gameweek"]] = row["projected_points"]

    totals = {}
    for player_id in player_ids:
        gw_points = by_player_gw.get(player_id, {})
        totals[player_id] = {
            horizon: sum(gw_points.get(start_gw + i, 0.0) for i in range(horizon)) for horizon in horizons
        }
    return totals


def upsert_squad_weakness(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        """
        INSERT INTO squad_weakness (manager_id, gw, player_id, replacement_gap, form_decline,
            fixture_swing, minutes_risk, weakness_score, weakness_rank, computed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(manager_id, gw, player_id) DO UPDATE SET
            replacement_gap=excluded.replacement_gap, form_decline=excluded.form_decline,
            fixture_swing=excluded.fixture_swing, minutes_risk=excluded.minutes_risk,
            weakness_score=excluded.weakness_score, weakness_rank=excluded.weakness_rank,
            computed_at=excluded.computed_at
        """,
        rows,
    )


def get_squad_weakness(conn: sqlite3.Connection, manager_id: int, gw: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM squad_weakness WHERE manager_id = ? AND gw = ? ORDER BY weakness_rank",
        (manager_id, gw),
    ).fetchall()
    return [dict(row) for row in rows]


def get_average_fixture_difficulty(conn: sqlite3.Connection, team_id: int, start_gw: int, num_gws: int) -> float | None:
    """Average fixture difficulty (from the team's own perspective) over
    [start_gw, start_gw + num_gws - 1]. None if the team has no fixtures in
    that window (e.g. a blank gameweek stretch)."""
    rows = conn.execute(
        "SELECT team_h, team_a, team_h_difficulty, team_a_difficulty FROM fixtures "
        "WHERE event BETWEEN ? AND ? AND (team_h = ? OR team_a = ?)",
        (start_gw, start_gw + num_gws - 1, team_id, team_id),
    ).fetchall()
    difficulties = [row["team_h_difficulty"] if row["team_h"] == team_id else row["team_a_difficulty"] for row in rows]
    if not difficulties:
        return None
    return sum(difficulties) / len(difficulties)
