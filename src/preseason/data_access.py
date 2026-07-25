"""Read helpers for the pre-season squad selector."""
import sqlite3


def get_previous_season_stats(conn: sqlite3.Connection) -> dict[int, dict]:
    return {row["player_id"]: dict(row) for row in conn.execute("SELECT * FROM player_previous_season_stats")}


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,)
    ).fetchone()
    return row is not None


def get_friendly_appearances_summary(conn: sqlite3.Connection) -> dict[int, dict]:
    """player_id -> {minutes, goals, assists, appearances}, aggregated across
    all recorded pre-season friendlies. Returns {} if the (optional, not yet
    built) friendlies ingestion module has never created its table -- this
    enrichment layer is designed to be a no-op when absent, not an error.
    """
    if not _table_exists(conn, "friendly_appearances"):
        return {}

    rows = conn.execute(
        """
        SELECT player_id, SUM(minutes) AS minutes, SUM(goals) AS goals,
               SUM(assists) AS assists, COUNT(*) AS appearances
        FROM friendly_appearances
        GROUP BY player_id
        """
    ).fetchall()
    return {row["player_id"]: dict(row) for row in rows}


def get_preseason_creator_notes(conn: sqlite3.Connection, target_gw: int = 1) -> dict[int, list[dict]]:
    """player_id -> list of {sentiment, reasoning, creator} notes relevant to
    the given gameweek. Returns {} if Phase 7's `creator_insights` table
    doesn't exist yet -- this integration point is a documented no-op until
    that phase is built, not a hard dependency.
    """
    if not _table_exists(conn, "creator_insights"):
        return {}

    try:
        rows = conn.execute(
            "SELECT player_id, sentiment, reasoning, creator FROM creator_insights WHERE gameweek = ?", (target_gw,)
        ).fetchall()
    except sqlite3.OperationalError:
        # Table exists but not in the shape we expect -- treat as absent
        # rather than crashing the whole pre-season scoring run.
        return {}

    notes: dict[int, list[dict]] = {}
    for row in rows:
        notes.setdefault(row["player_id"], []).append(dict(row))
    return notes
