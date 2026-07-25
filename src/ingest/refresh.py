"""Refresh the local SQLite store from the official FPL API.

Run this once to set up the DB, and rerun each gameweek to pick up new
prices, ownership, form, and fixture results.

Usage:
    python -m src.ingest.refresh                # bootstrap-static + fixtures
    python -m src.ingest.refresh --with-history  # also pull per-player gw history
"""
import argparse
import logging
import time
from datetime import datetime, timezone

from src.db import connection, init_db
from src.ingest import api_client

logger = logging.getLogger(__name__)

HISTORY_REQUEST_DELAY_SECONDS = 0.1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def refresh_teams(conn, teams: list[dict], pulled_at: str) -> None:
    rows = [
        (
            t["id"],
            t["name"],
            t.get("short_name"),
            t.get("strength"),
            t.get("strength_overall_home"),
            t.get("strength_overall_away"),
            t.get("strength_attack_home"),
            t.get("strength_attack_away"),
            t.get("strength_defence_home"),
            t.get("strength_defence_away"),
            pulled_at,
        )
        for t in teams
    ]
    conn.executemany(
        """
        INSERT INTO teams (
            id, name, short_name, strength, strength_overall_home, strength_overall_away,
            strength_attack_home, strength_attack_away, strength_defence_home, strength_defence_away, pulled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, short_name=excluded.short_name, strength=excluded.strength,
            strength_overall_home=excluded.strength_overall_home, strength_overall_away=excluded.strength_overall_away,
            strength_attack_home=excluded.strength_attack_home, strength_attack_away=excluded.strength_attack_away,
            strength_defence_home=excluded.strength_defence_home, strength_defence_away=excluded.strength_defence_away,
            pulled_at=excluded.pulled_at
        """,
        rows,
    )
    logger.info("Refreshed %d teams", len(rows))


def refresh_events(conn, events: list[dict], pulled_at: str) -> None:
    rows = [
        (
            e["id"],
            e.get("name"),
            e.get("deadline_time"),
            int(bool(e.get("finished"))),
            int(bool(e.get("is_previous"))),
            int(bool(e.get("is_current"))),
            int(bool(e.get("is_next"))),
            e.get("average_entry_score"),
            e.get("highest_score"),
            pulled_at,
        )
        for e in events
    ]
    conn.executemany(
        """
        INSERT INTO events (
            id, name, deadline_time, finished, is_previous, is_current, is_next,
            average_entry_score, highest_score, pulled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, deadline_time=excluded.deadline_time, finished=excluded.finished,
            is_previous=excluded.is_previous, is_current=excluded.is_current, is_next=excluded.is_next,
            average_entry_score=excluded.average_entry_score, highest_score=excluded.highest_score,
            pulled_at=excluded.pulled_at
        """,
        rows,
    )
    logger.info("Refreshed %d events (gameweeks)", len(rows))


def refresh_players(conn, players: list[dict], pulled_at: str) -> None:
    rows = [
        (
            p["id"],
            p["team"],
            p.get("first_name"),
            p.get("second_name"),
            p.get("web_name"),
            p.get("element_type"),
            p.get("now_cost"),
            _to_float(p.get("selected_by_percent")),
            _to_float(p.get("form")),
            p.get("total_points"),
            p.get("minutes"),
            p.get("goals_scored"),
            p.get("assists"),
            p.get("clean_sheets"),
            p.get("goals_conceded"),
            _to_float(p.get("expected_goals")),
            _to_float(p.get("expected_assists")),
            _to_float(p.get("expected_goal_involvements")),
            _to_float(p.get("expected_goals_conceded")),
            _to_float(p.get("ict_index")),
            _to_float(p.get("influence")),
            _to_float(p.get("creativity")),
            _to_float(p.get("threat")),
            p.get("bonus"),
            p.get("bps"),
            p.get("status"),
            _to_float(p.get("chance_of_playing_next_round")),
            _to_float(p.get("chance_of_playing_this_round")),
            _to_float(p.get("points_per_game")),
            _to_float(p.get("value_season")),
            pulled_at,
        )
        for p in players
    ]
    conn.executemany(
        """
        INSERT INTO players (
            id, team_id, first_name, second_name, web_name, element_type, now_cost,
            selected_by_percent, form, total_points, minutes, goals_scored, assists,
            clean_sheets, goals_conceded, expected_goals, expected_assists,
            expected_goal_involvements, expected_goals_conceded, ict_index, influence,
            creativity, threat, bonus, bps, status, chance_of_playing_next_round,
            chance_of_playing_this_round, points_per_game, value_season, pulled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            team_id=excluded.team_id, first_name=excluded.first_name, second_name=excluded.second_name,
            web_name=excluded.web_name, element_type=excluded.element_type, now_cost=excluded.now_cost,
            selected_by_percent=excluded.selected_by_percent, form=excluded.form, total_points=excluded.total_points,
            minutes=excluded.minutes, goals_scored=excluded.goals_scored, assists=excluded.assists,
            clean_sheets=excluded.clean_sheets, goals_conceded=excluded.goals_conceded,
            expected_goals=excluded.expected_goals, expected_assists=excluded.expected_assists,
            expected_goal_involvements=excluded.expected_goal_involvements,
            expected_goals_conceded=excluded.expected_goals_conceded, ict_index=excluded.ict_index,
            influence=excluded.influence, creativity=excluded.creativity, threat=excluded.threat,
            bonus=excluded.bonus, bps=excluded.bps, status=excluded.status,
            chance_of_playing_next_round=excluded.chance_of_playing_next_round,
            chance_of_playing_this_round=excluded.chance_of_playing_this_round,
            points_per_game=excluded.points_per_game, value_season=excluded.value_season,
            pulled_at=excluded.pulled_at
        """,
        rows,
    )
    logger.info("Refreshed %d players", len(rows))


def refresh_fixtures(conn, fixtures: list[dict], pulled_at: str) -> None:
    rows = [
        (
            f["id"],
            f.get("event"),
            f.get("team_h"),
            f.get("team_a"),
            f.get("team_h_score"),
            f.get("team_a_score"),
            f.get("kickoff_time"),
            int(bool(f.get("finished"))),
            f.get("team_h_difficulty"),
            f.get("team_a_difficulty"),
            pulled_at,
        )
        for f in fixtures
    ]
    conn.executemany(
        """
        INSERT INTO fixtures (
            id, event, team_h, team_a, team_h_score, team_a_score, kickoff_time,
            finished, team_h_difficulty, team_a_difficulty, pulled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            event=excluded.event, team_h=excluded.team_h, team_a=excluded.team_a,
            team_h_score=excluded.team_h_score, team_a_score=excluded.team_a_score,
            kickoff_time=excluded.kickoff_time, finished=excluded.finished,
            team_h_difficulty=excluded.team_h_difficulty, team_a_difficulty=excluded.team_a_difficulty,
            pulled_at=excluded.pulled_at
        """,
        rows,
    )
    logger.info("Refreshed %d fixtures", len(rows))


def refresh_gameweek_history(conn, player_ids: list[int], pulled_at: str) -> None:
    """Pull per-GW history for every player. Slow (one request per player)."""
    total = len(player_ids)
    for i, player_id in enumerate(player_ids, start=1):
        try:
            summary = api_client.get_element_summary(player_id)
        except RuntimeError as exc:
            logger.warning("Skipping player %d: %s", player_id, exc)
            continue

        history = summary.get("history", [])
        rows = [
            (
                player_id,
                h["round"],
                h.get("fixture"),
                h.get("opponent_team"),
                int(bool(h.get("was_home"))),
                h.get("total_points"),
                h.get("minutes"),
                h.get("goals_scored"),
                h.get("assists"),
                h.get("clean_sheets"),
                h.get("goals_conceded"),
                _to_float(h.get("expected_goals")),
                _to_float(h.get("expected_assists")),
                _to_float(h.get("expected_goal_involvements")),
                _to_float(h.get("expected_goals_conceded")),
                h.get("bps"),
                h.get("bonus"),
                _to_float(h.get("influence")),
                _to_float(h.get("creativity")),
                _to_float(h.get("threat")),
                _to_float(h.get("ict_index")),
                h.get("value"),
                pulled_at,
            )
            for h in history
        ]
        if rows:
            conn.executemany(
                """
                INSERT INTO gameweek_stats (
                    player_id, gw, fixture_id, opponent_team, was_home, total_points, minutes,
                    goals_scored, assists, clean_sheets, goals_conceded, expected_goals,
                    expected_assists, expected_goal_involvements, expected_goals_conceded,
                    bps, bonus, influence, creativity, threat, ict_index, value, pulled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, gw) DO UPDATE SET
                    fixture_id=excluded.fixture_id, opponent_team=excluded.opponent_team,
                    was_home=excluded.was_home, total_points=excluded.total_points, minutes=excluded.minutes,
                    goals_scored=excluded.goals_scored, assists=excluded.assists, clean_sheets=excluded.clean_sheets,
                    goals_conceded=excluded.goals_conceded, expected_goals=excluded.expected_goals,
                    expected_assists=excluded.expected_assists,
                    expected_goal_involvements=excluded.expected_goal_involvements,
                    expected_goals_conceded=excluded.expected_goals_conceded, bps=excluded.bps,
                    bonus=excluded.bonus, influence=excluded.influence, creativity=excluded.creativity,
                    threat=excluded.threat, ict_index=excluded.ict_index, value=excluded.value,
                    pulled_at=excluded.pulled_at
                """,
                rows,
            )

        if i % 50 == 0 or i == total:
            logger.info("Fetched gameweek history for %d/%d players", i, total)
        time.sleep(HISTORY_REQUEST_DELAY_SECONDS)


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run(with_history: bool = False) -> None:
    init_db()
    pulled_at = _now()

    logger.info("Fetching bootstrap-static...")
    bootstrap = api_client.get_bootstrap_static()

    logger.info("Fetching fixtures...")
    fixtures = api_client.get_fixtures()

    with connection() as conn:
        refresh_teams(conn, bootstrap["teams"], pulled_at)
        refresh_events(conn, bootstrap["events"], pulled_at)
        refresh_players(conn, bootstrap["elements"], pulled_at)
        refresh_fixtures(conn, fixtures, pulled_at)

        if with_history:
            player_ids = [p["id"] for p in bootstrap["elements"]]
            logger.info("Fetching per-player gameweek history for %d players (this may take a while)...", len(player_ids))
            refresh_gameweek_history(conn, player_ids, pulled_at)

    logger.info("Refresh complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-history",
        action="store_true",
        help="Also pull per-player gameweek history via element-summary (one request per player, slower).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    run(with_history=args.with_history)


if __name__ == "__main__":
    main()
