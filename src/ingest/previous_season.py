"""Pull each current player's most recent past-season aggregate stats.

Before GW1, `gameweek_stats` is empty for everyone -- there's no current-season
signal at all yet. `element-summary`'s `history_past` gives season-by-season
totals (points, minutes, xG, xA, ...) per player, which Phase 8's pre-season
scorer uses as its primary input instead.

Players with no `history_past` at all (rookies, promoted-team debutants,
first-ever PL season, overseas signings new to the league) are simply
skipped rather than stored with placeholder values -- their absence from
this table *is* the signal the pre-season confidence flag reads.

    python -m src.ingest.previous_season
"""
import argparse
import logging
import time
from datetime import datetime, timezone

from src.db import connection
from src.ingest import api_client

logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = 0.1


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_previous_season_stats(conn, player_ids: list[int], pulled_at: str | None = None) -> int:
    """Stores the most recent entry in each player's `history_past` (FPL
    returns these in chronological order, so the last entry is last season)
    in `player_previous_season_stats`. Returns the number of players stored.
    """
    pulled_at = pulled_at or datetime.now(timezone.utc).isoformat()
    total = len(player_ids)
    stored = 0

    for i, player_id in enumerate(player_ids, start=1):
        try:
            summary = api_client.get_element_summary(player_id)
        except RuntimeError as exc:
            logger.warning("Skipping player %d: %s", player_id, exc)
            continue

        history_past = summary.get("history_past", [])
        if not history_past:
            continue
        last_season = history_past[-1]

        conn.execute(
            """
            INSERT INTO player_previous_season_stats (
                player_id, season_name, minutes, total_points, goals_scored, assists,
                clean_sheets, goals_conceded, expected_goals, expected_assists,
                expected_goal_involvements, expected_goals_conceded, saves, bonus,
                start_cost, end_cost, pulled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                season_name=excluded.season_name, minutes=excluded.minutes,
                total_points=excluded.total_points, goals_scored=excluded.goals_scored,
                assists=excluded.assists, clean_sheets=excluded.clean_sheets,
                goals_conceded=excluded.goals_conceded, expected_goals=excluded.expected_goals,
                expected_assists=excluded.expected_assists,
                expected_goal_involvements=excluded.expected_goal_involvements,
                expected_goals_conceded=excluded.expected_goals_conceded, saves=excluded.saves,
                bonus=excluded.bonus, start_cost=excluded.start_cost, end_cost=excluded.end_cost,
                pulled_at=excluded.pulled_at
            """,
            (
                player_id, last_season.get("season_name"), last_season.get("minutes"),
                last_season.get("total_points"), last_season.get("goals_scored"), last_season.get("assists"),
                last_season.get("clean_sheets"), last_season.get("goals_conceded"),
                _to_float(last_season.get("expected_goals")), _to_float(last_season.get("expected_assists")),
                _to_float(last_season.get("expected_goal_involvements")), _to_float(last_season.get("expected_goals_conceded")),
                last_season.get("saves"), last_season.get("bonus"),
                last_season.get("start_cost"), last_season.get("end_cost"), pulled_at,
            ),
        )
        stored += 1

        if i % 50 == 0 or i == total:
            logger.info("Fetched previous-season stats for %d/%d players", i, total)
        time.sleep(REQUEST_DELAY_SECONDS)

    return stored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    with connection() as conn:
        player_ids = [row["id"] for row in conn.execute("SELECT id FROM players")]
        logger.info("Fetching previous-season stats for %d players...", len(player_ids))
        stored = fetch_previous_season_stats(conn, player_ids)

    logger.info("Stored previous-season stats for %d/%d players.", stored, len(player_ids))


if __name__ == "__main__":
    main()
