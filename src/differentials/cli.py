"""Mini-league differential finder.

    python -m src.differentials.cli                      # full report for the configured league
    python -m src.differentials.cli --league-id 12345     # override the configured league
    python -m src.differentials.cli --top 10 --no-refresh

Prints, for the configured mini-league (LEAGUE_ID lives in src/config.py --
change only that constant once your real league is created):
  - top differentials worth transferring in (low in-league ownership, strong projection)
  - differentials you already own
  - high-owned "safe" picks in the league, so you know your shared exposure
  - a rival chip-usage summary
"""
import argparse
import logging

from src.chips import constants as chip_constants
from src.config import DEFAULT_LEAGUE_ID, DEFAULT_MANAGER_ID
from src.db import connection
from src.differentials import chip_summary, data_access, finder, ingestion
from src.scoring import data_access as scoring_data_access
from src.transfers import data_access as transfers_data_access

logger = logging.getLogger(__name__)


def _format_row(row: dict, players_by_id: dict, teams: dict) -> str:
    player = players_by_id.get(row["player_id"], {})
    team = teams.get(player.get("team_id"), "?")
    name = player.get("web_name", f"#{row['player_id']}")
    gains = row["projected_points"]
    gain_str = "  ".join(f"{h}GW: {gains.get(h, 0.0):.1f}" for h in sorted(gains))
    return (
        f"{name:<20}{team:<6} {gain_str}  |  owned {row['ownership_pct']:.0f}%  "
        f"captained {row['captaincy_pct']:.0f}%"
    )


def run(
    league_id: int = DEFAULT_LEAGUE_ID,
    my_manager_id: int = DEFAULT_MANAGER_ID,
    top_n: int = 10,
    refresh: bool = True,
    max_ownership_pct: float = 30.0,
    min_high_owned_pct: float = 50.0,
) -> None:
    with connection() as conn:
        current_gw = scoring_data_access.get_current_gw(conn)

        if refresh:
            ingestion.fetch_league_managers(conn, league_id)
            ingestion.fetch_league_picks(conn, league_id, gw=current_gw)

        league_gw = data_access.get_latest_league_picks_gw(conn, league_id)
        if league_gw is None:
            print(f"No league pick data yet for league {league_id}. Run without --no-refresh first.")
            return

        my_squad_gw = transfers_data_access.get_latest_squad_gw(conn, my_manager_id)

        players_by_id = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM players")}
        teams = {row["id"]: (row["short_name"] or row["name"]) for row in conn.execute("SELECT id, name, short_name FROM teams")}

        print(f"\nDifferential report for league {league_id}, GW{current_gw} (picks from GW{league_gw})")

        to_transfer_in = finder.rank_differentials_to_transfer_in(
            conn, league_id, my_manager_id, league_gw, my_squad_gw, start_gw=current_gw,
            top_n=top_n, max_ownership_pct=max_ownership_pct,
        )
        print(f"\nTop {top_n} differentials to consider (<= {max_ownership_pct:.0f}% owned in your league):")
        if not to_transfer_in:
            print("  (none found -- try raising --max-ownership)")
        for row in to_transfer_in:
            print("  " + _format_row(row, players_by_id, teams))

        my_differentials = finder.rank_my_differentials(
            conn, league_id, my_manager_id, league_gw, my_squad_gw, start_gw=current_gw,
            top_n=top_n, max_ownership_pct=max_ownership_pct,
        )
        print("\nDifferentials you already own:")
        if not my_differentials:
            print("  (none of your squad qualifies -- try raising --max-ownership, or run "
                  "`python -m src.transfers.cli` first if you have no squad snapshot yet)")
        for row in my_differentials:
            print("  " + _format_row(row, players_by_id, teams))

        high_owned = finder.rank_high_owned(
            conn, league_id, league_gw, start_gw=current_gw, min_ownership_pct=min_high_owned_pct, top_n=top_n,
        )
        print(f"\nHigh-owned picks in your league (>= {min_high_owned_pct:.0f}%) -- your shared exposure:")
        if not high_owned:
            print("  (none)")
        for row in high_owned:
            print("  " + _format_row(row, players_by_id, teams))

        print("\nRival chip usage:")
        summary = chip_summary.fetch_rival_chip_usage(conn, league_id, current_gw, refresh=refresh)
        for manager_id, info in summary.items():
            used = ", ".join(
                f"{chip_constants.CHIP_DISPLAY_NAMES.get(c['chip_name'], c['chip_name'])} (GW{c['event']})"
                for c in info["chips_used"]
            ) or "none yet"
            team_name = info.get("team_name") or f"Manager {manager_id}"
            print(f"  {team_name}: {used}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--league-id", type=int, default=DEFAULT_LEAGUE_ID)
    parser.add_argument("--manager-id", type=int, default=DEFAULT_MANAGER_ID)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--max-ownership", type=float, default=30.0, help="Max in-league ownership %% to count as a differential.")
    parser.add_argument("--high-owned-threshold", type=float, default=50.0)
    parser.add_argument("--no-refresh", dest="refresh", action="store_false")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    run(
        league_id=args.league_id,
        my_manager_id=args.manager_id,
        top_n=args.top,
        refresh=args.refresh,
        max_ownership_pct=args.max_ownership,
        min_high_owned_pct=args.high_owned_threshold,
    )


if __name__ == "__main__":
    main()
