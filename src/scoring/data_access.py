"""Read/write helpers for the scoring engine. Keeps SQL out of the model code."""
import sqlite3


def get_current_gw(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM events WHERE is_current = 1").fetchone()
    if row:
        return row["id"]
    row = conn.execute("SELECT id FROM events WHERE is_next = 1").fetchone()
    if row:
        return row["id"]
    row = conn.execute("SELECT MAX(id) AS max_id FROM events WHERE finished = 1").fetchone()
    if row and row["max_id"]:
        return row["max_id"] + 1
    return 1


def get_teams(conn: sqlite3.Connection) -> dict[int, dict]:
    return {row["id"]: dict(row) for row in conn.execute("SELECT * FROM teams")}


def get_players(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT * FROM players")]


def get_all_player_histories(conn: sqlite3.Connection, as_of_gw: int | None = None) -> dict[int, list[dict]]:
    """player_id -> gameweek_stats rows, sorted ascending by gameweek.

    Pass `as_of_gw` to restrict to gameweeks strictly before it -- used by the
    backtest to avoid look-ahead bias.
    """
    query = "SELECT * FROM gameweek_stats"
    params: tuple = ()
    if as_of_gw is not None:
        query += " WHERE gw < ?"
        params = (as_of_gw,)
    query += " ORDER BY player_id ASC, gw ASC"

    histories: dict[int, list[dict]] = {}
    for row in conn.execute(query, params):
        histories.setdefault(row["player_id"], []).append(dict(row))
    return histories


def get_previous_season_stats(conn: sqlite3.Connection) -> dict[int, dict]:
    return {row["player_id"]: dict(row) for row in conn.execute("SELECT * FROM player_previous_season_stats")}


def get_team_fixtures_map(conn: sqlite3.Connection, start_gw: int, end_gw: int) -> dict[int, dict[int, list[dict]]]:
    """team_id -> gameweek -> list of {opponent_team, is_home, difficulty}.

    A team with two entries for the same gameweek is a double gameweek; a
    team with none for a gameweek in range is a blank.
    """
    rows = conn.execute(
        "SELECT * FROM fixtures WHERE event BETWEEN ? AND ?", (start_gw, end_gw)
    ).fetchall()

    team_map: dict[int, dict[int, list[dict]]] = {}
    for row in rows:
        gw = row["event"]
        if gw is None:
            continue
        team_map.setdefault(row["team_h"], {}).setdefault(gw, []).append(
            {"opponent_team": row["team_a"], "is_home": True, "difficulty": row["team_h_difficulty"]}
        )
        team_map.setdefault(row["team_a"], {}).setdefault(gw, []).append(
            {"opponent_team": row["team_h"], "is_home": False, "difficulty": row["team_a_difficulty"]}
        )
    return team_map


def upsert_projections(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        """
        INSERT INTO player_projections (player_id, gameweek, projected_points, confidence, computed_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(player_id, gameweek) DO UPDATE SET
            projected_points=excluded.projected_points, confidence=excluded.confidence,
            computed_at=excluded.computed_at
        """,
        rows,
    )


def get_horizon_projection(conn: sqlite3.Connection, player_id: int, start_gw: int, num_gws: int) -> tuple[float, float]:
    """Sum of projected points and average confidence across [start_gw, start_gw+num_gws-1]."""
    rows = conn.execute(
        "SELECT projected_points, confidence FROM player_projections "
        "WHERE player_id = ? AND gameweek BETWEEN ? AND ?",
        (player_id, start_gw, start_gw + num_gws - 1),
    ).fetchall()
    if not rows:
        return 0.0, 0.0
    total_points = sum(r["projected_points"] for r in rows)
    avg_confidence = sum(r["confidence"] for r in rows) / len(rows)
    return round(total_points, 2), round(avg_confidence, 3)
