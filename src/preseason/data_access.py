"""Read helpers for the pre-season squad selector."""
import sqlite3

from src.scoring import data_access as scoring_data_access


def get_previous_season_stats(conn: sqlite3.Connection) -> dict[int, dict]:
    return {row["player_id"]: dict(row) for row in conn.execute("SELECT * FROM player_previous_season_stats")}


def get_team_fixture_ticker(conn: sqlite3.Connection, start_gw: int, num_gws: int) -> dict[int, list[str]]:
    """team_id -> one difficulty label per gameweek in
    [start_gw, start_gw + num_gws - 1]. A double gameweek joins both
    fixtures' difficulty with "/"; a blank gameweek shows "-". Reuses the
    same team-fixtures lookup Phase 2's scoring engine and the transfer/chip
    modules already rely on, so this always matches what actually drove the
    pre-season score.
    """
    fixtures_map = scoring_data_access.get_team_fixtures_map(conn, start_gw, start_gw + num_gws - 1)
    all_team_ids = [row["id"] for row in conn.execute("SELECT id FROM teams")]

    ticker = {}
    for team_id in all_team_ids:
        team_fixtures = fixtures_map.get(team_id, {})
        labels = []
        for gw in range(start_gw, start_gw + num_gws):
            fixtures_this_gw = team_fixtures.get(gw, [])
            if not fixtures_this_gw:
                labels.append("-")
            else:
                labels.append("/".join(str(f["difficulty"] if f["difficulty"] is not None else "?") for f in fixtures_this_gw))
        ticker[team_id] = labels
    return ticker


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
