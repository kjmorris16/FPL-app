"""Pre-season squad selector quick check: prints the suggested 15-man squad
and starting XI, so it can be sanity-checked against known team news before
relying on it for a real GW1 squad.

    python -m src.preseason.cli
    python -m src.preseason.cli --budget 985 --horizon 3
"""
import argparse

from src.db import connection
from src.preseason import constants as c, optimizer, scoring


def _format_price(tenths: int) -> str:
    return f"£{tenths / 10:.1f}m"


def _print_player_row(player: dict, players_by_id: dict, teams: dict) -> None:
    info = players_by_id.get(player["player_id"], {})
    team = teams.get(info.get("team_id"), "?")
    name = info.get("web_name", f"#{player['player_id']}")
    print(f"    {name:<20}{team:<6}{_format_price(info.get('now_cost', 0)):>8}  score={player['score']:>6.2f}  conf={player['confidence']:.2f}")


def run(budget: int = c.DEFAULT_BUDGET_TENTHS, horizon_gws: int = c.FIXTURE_HORIZON_GWS) -> None:
    with connection() as conn:
        scores = scoring.compute_preseason_scores(conn, start_gw=c.START_GW, horizon_gws=horizon_gws)
        players_by_id = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM players")}
        teams = {row["id"]: (row["short_name"] or row["name"]) for row in conn.execute("SELECT id, name, short_name FROM teams")}

    candidates = [
        {
            "player_id": pid,
            "element_type": players_by_id[pid]["element_type"],
            "team_id": players_by_id[pid]["team_id"],
            "now_cost": players_by_id[pid]["now_cost"] or 0,
            "score": info["score"],
            "confidence": info["confidence"],
            "notes": info["notes"],
        }
        for pid, info in scores.items()
        if pid in players_by_id
    ]

    squad = optimizer.select_best_squad(candidates, budget=budget)
    lineup = optimizer.select_starting_xi(squad)

    print(f"\nSuggested GW1 squad (budget £{budget / 10:.1f}m)\n")
    for position, label in ((c.GK, "Goalkeepers"), (c.DEF, "Defenders"), (c.MID, "Midfielders"), (c.FWD, "Forwards")):
        print(f"{label}:")
        for player in sorted((p for p in squad if p["element_type"] == position), key=lambda p: p["score"], reverse=True):
            _print_player_row(player, players_by_id, teams)

    total_cost = sum(players_by_id[p["player_id"]]["now_cost"] or 0 for p in squad)
    print(f"\nTotal cost: {_format_price(total_cost)}  (bank: {_format_price(budget - total_cost)})")

    print(f"\nSuggested starting XI ({lineup['formation']}):")
    for player in lineup["starting_xi"]:
        _print_player_row(player, players_by_id, teams)

    print("\nBench:")
    for player in lineup["bench"]:
        _print_player_row(player, players_by_id, teams)

    ranked_xi = sorted(lineup["starting_xi"], key=lambda p: p["score"], reverse=True)
    captain, vice = ranked_xi[0], ranked_xi[1]
    print(f"\nCaptain: {players_by_id[captain['player_id']]['web_name']} (score {captain['score']:.2f})")
    print(f"Vice-captain: {players_by_id[vice['player_id']]['web_name']} (score {vice['score']:.2f})")

    for player in squad:
        notes = player.get("notes")
        if notes:
            name = players_by_id[player["player_id"]]["web_name"]
            for note in notes:
                print(f"\nNote ({name}): {note}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--budget", type=float, default=c.DEFAULT_BUDGET_TENTHS / 10, help="Squad budget in £m (default: 100.0).")
    parser.add_argument("--horizon", type=int, default=c.FIXTURE_HORIZON_GWS, help="Opening gameweeks to project across.")
    args = parser.parse_args()
    run(budget=round(args.budget * 10), horizon_gws=args.horizon)


if __name__ == "__main__":
    main()
