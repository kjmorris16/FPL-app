"""Chip planner quick check: print the top candidate gameweeks for each chip
you still have available, plus a single top recommendation per chip.

    python -m src.chips.cli
    python -m src.chips.cli --horizon 15 --top 5
    python -m src.chips.cli --full-calendar        # print every gameweek's notes too
"""
import argparse

from src.chips import availability, constants as c, planner
from src.config import DEFAULT_MANAGER_ID
from src.db import connection
from src.ingest import manager as manager_ingest
from src.scoring import data_access as scoring_data_access
from src.transfers import data_access as transfers_data_access


def run(
    manager_id: int = DEFAULT_MANAGER_ID,
    horizon_gws: int = c.PLANNING_HORIZON_GWS,
    refresh_chip_usage: bool = True,
    top_n: int = 3,
    full_calendar: bool = False,
) -> None:
    with connection() as conn:
        current_gw = scoring_data_access.get_current_gw(conn)
        end_gw = current_gw + horizon_gws - 1

        if refresh_chip_usage:
            manager_ingest.fetch_chip_usage(conn, manager_id)

        chip_usage = [
            dict(row) for row in conn.execute("SELECT chip_name, event FROM chip_usage WHERE manager_id = ?", (manager_id,))
        ]
        available = availability.get_available_chips(chip_usage, current_gw)

        squad_gw = transfers_data_access.get_latest_squad_gw(conn, manager_id)
        calendar = planner.build_calendar(conn, manager_id, current_gw, end_gw, squad_gw=squad_gw)

        teams = {row["id"]: (row["short_name"] or row["name"]) for row in conn.execute("SELECT id, name, short_name FROM teams")}
        players_by_id = {row["id"]: dict(row) for row in conn.execute("SELECT id, web_name FROM players")}

        print(f"\nChip planner for GW{current_gw}-GW{end_gw} (manager {manager_id})")
        if squad_gw is None:
            print("(no squad snapshot found -- Bench Boost/Triple Captain/Free Hit values need "
                  "`python -m src.transfers.cli` run at least once; Wildcard timing works regardless.)")

        for chip_name, display_name in c.CHIP_DISPLAY_NAMES.items():
            print(f"\n{display_name}:")
            if not available.get(chip_name):
                print("  Already used (or no half remaining for this season).")
                continue

            ranked = planner.top_n_gameweeks(calendar, chip_name, n=top_n)
            if not ranked:
                print("  (no signal yet)")
                continue
            for entry in ranked:
                print(f"  {planner.describe_recommendation(chip_name, entry, teams=teams, players_by_id=players_by_id)}")

        if full_calendar:
            print(f"\nFull calendar, GW{current_gw}-GW{end_gw}:")
            for entry in calendar:
                if entry["notes"]:
                    print(f"  GW{entry['gw']}: {'; '.join(entry['notes'])}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manager-id", type=int, default=DEFAULT_MANAGER_ID)
    parser.add_argument("--horizon", type=int, default=c.PLANNING_HORIZON_GWS, help="How many gameweeks ahead to plan.")
    parser.add_argument("--top", type=int, default=3, help="Number of candidate gameweeks to show per chip.")
    parser.add_argument("--no-refresh-chip-usage", dest="refresh_chip_usage", action="store_false")
    parser.add_argument("--full-calendar", action="store_true", help="Also print every gameweek's DGW/BGW notes.")
    args = parser.parse_args()

    run(
        manager_id=args.manager_id,
        horizon_gws=args.horizon,
        refresh_chip_usage=args.refresh_chip_usage,
        top_n=args.top,
        full_calendar=args.full_calendar,
    )


if __name__ == "__main__":
    main()
