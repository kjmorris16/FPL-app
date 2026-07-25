"""Quick sanity-check CLI: print the top projected players for a gameweek.

    python -m src.scoring.cli                     # top 15 for the current/next GW
    python -m src.scoring.cli --gw 5 --top 20
    python -m src.scoring.cli --recompute          # recompute projections first
"""
import argparse

from src.db import connection
from src.scoring import confidence, constants as c, data_access, projections


def print_top(conn, gw: int, top_n: int = 15) -> None:
    players = {p["id"]: p for p in data_access.get_players(conn)}
    teams = data_access.get_teams(conn)
    rows = conn.execute(
        "SELECT player_id, projected_points, confidence FROM player_projections WHERE gameweek = ?",
        (gw,),
    ).fetchall()
    ranked = sorted(rows, key=lambda r: r["projected_points"], reverse=True)[:top_n]

    print(f"\nTop {top_n} projected players for GW{gw}\n")
    print(f"{'Player':<20}{'Team':<6}{'Pos':<5}{'xPts':>7}  {'Confidence'}")
    print("-" * 55)
    for row in ranked:
        player = players.get(row["player_id"])
        if not player:
            continue
        team = teams.get(player["team_id"], {})
        pos = c.POSITION_NAMES.get(player["element_type"], "?")
        label = confidence.confidence_label(row["confidence"])
        print(
            f"{player['web_name']:<20}{team.get('short_name', '?'):<6}{pos:<5}"
            f"{row['projected_points']:>7.2f}  {label}"
        )
    if not ranked:
        print("(no projections found -- run with --recompute, or make sure "
              "`python -m src.ingest.refresh` has been run first)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gw", type=int, default=None, help="Gameweek to show (default: current/next GW).")
    parser.add_argument("--top", type=int, default=15, help="Number of players to show.")
    parser.add_argument("--recompute", action="store_true", help="Recompute projections before printing.")
    args = parser.parse_args()

    with connection() as conn:
        gw = args.gw or data_access.get_current_gw(conn)
        if args.recompute:
            rows = projections.compute_projections(conn, gw, horizon_gws=1)
            data_access.upsert_projections(conn, rows)
            conn.commit()
        print_top(conn, gw, args.top)


if __name__ == "__main__":
    main()
