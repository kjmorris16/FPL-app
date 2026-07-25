"""Read helpers for the differential finder. Keeps SQL out of the model code."""
import sqlite3


def get_league_managers(conn: sqlite3.Connection, league_id: int) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT * FROM league_managers WHERE league_id = ?", (league_id,))]


def get_latest_league_picks_gw(conn: sqlite3.Connection, league_id: int) -> int | None:
    row = conn.execute(
        "SELECT MAX(gw) AS gw FROM league_manager_picks WHERE league_id = ?", (league_id,)
    ).fetchone()
    return row["gw"] if row and row["gw"] is not None else None


def get_league_picks(conn: sqlite3.Connection, league_id: int, gw: int) -> list[dict]:
    return [
        dict(row) for row in conn.execute(
            "SELECT * FROM league_manager_picks WHERE league_id = ? AND gw = ?", (league_id, gw)
        )
    ]


def get_managers_with_picks(conn: sqlite3.Connection, league_id: int, gw: int) -> list[int]:
    return [
        row["manager_id"] for row in conn.execute(
            "SELECT DISTINCT manager_id FROM league_manager_picks WHERE league_id = ? AND gw = ?", (league_id, gw)
        )
    ]
