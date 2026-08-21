"""Weekly routine: pull my live squad, rank transfer combinations, and print
the top recommendation plus a captain/vice pick.

    python -m src.transfers.cli                       # everything, defaults
    python -m src.transfers.cli --gw 12
    python -m src.transfers.cli --free-transfers 2     # override the reconstructed FT count
    python -m src.transfers.cli --no-refresh-squad     # use the last-pulled squad snapshot
    python -m src.transfers.cli --top 3
"""
import argparse
import logging

from src.config import DEFAULT_MANAGER_ID
from src.db import connection
from src.ingest import manager as manager_ingest
from src.scoring import data_access as scoring_data_access, projections
from src.transfers import captain, constants as c, data_access, optimizer, rationale

logger = logging.getLogger(__name__)


def _format_price(tenths: int) -> str:
    return f"£{tenths / 10:.1f}m"


def _print_combo(rank: int, combo: optimizer.TransferCombo) -> None:
    if not combo.swaps:
        print(f"\n#{rank}. Make no transfers")
    else:
        for swap in combo.swaps:
            print(f"\n#{rank}. OUT {swap.out_player['web_name']} -> IN {swap.in_player['web_name']}")

    horizons = c.REPORTED_HORIZONS_GWS
    gain_str = "  ".join(f"{h}GW: {combo.gains[h]:+.1f}" for h in horizons)
    print(f"    Projected gain -- {gain_str}")
    if combo.hit_cost:
        net_str = "  ".join(f"{h}GW: {combo.net_gains[h]:+.1f}" for h in horizons)
        print(f"    Hit cost: -{combo.hit_cost}  |  Net -- {net_str}")
    print(f"    Remaining bank: {_format_price(combo.remaining_bank)}")


def run(
    manager_id: int = DEFAULT_MANAGER_ID,
    gw: int | None = None,
    free_transfers_override: int | None = None,
    refresh_squad: bool = True,
    recompute_projections: bool = True,
    top_n: int = 5,
) -> None:
    with connection() as conn:
        if refresh_squad:
            snapshot = manager_ingest.fetch_squad_snapshot(conn, manager_id, gw=gw)
            gw = snapshot["gw"]
        else:
            gw = gw or data_access.get_latest_squad_gw(conn, manager_id)
            if gw is None:
                raise RuntimeError(
                    f"No squad snapshot found for manager {manager_id}. "
                    "Run once without --no-refresh-squad first."
                )

        if recompute_projections:
            rows = projections.compute_projections(conn, start_gw=gw, horizon_gws=c.DEFAULT_RANKING_HORIZON_GWS)
            scoring_data_access.upsert_projections(conn, rows)

        manager_snapshot = data_access.get_manager_snapshot(conn, manager_id, gw)
        if manager_snapshot is None:
            raise RuntimeError(f"No manager snapshot for GW{gw} -- run with --refresh-squad first.")

        bank = manager_snapshot["bank"]
        free_transfers = free_transfers_override if free_transfers_override is not None else manager_snapshot["free_transfers"]

        squad = data_access.get_current_squad(conn, manager_id, gw)
        candidate_pool = data_access.get_candidate_pool(conn)

        all_ids = {p["player_id"] for p in squad} | {p["player_id"] for p in candidate_pool}
        proj_totals = data_access.get_projection_totals(conn, list(all_ids), start_gw=gw, horizons=c.REPORTED_HORIZONS_GWS)

        combos = optimizer.generate_combos(squad, candidate_pool, bank, free_transfers, proj_totals)

        print(f"\nTransfer recommendations for GW{gw} (manager {manager_id})")
        print(f"Bank: {_format_price(bank)}  |  Free transfers: {free_transfers}")

        for rank, combo in enumerate(combos[:top_n], start=1):
            _print_combo(rank, combo)

        top_combo = combos[0]
        fixture_context = {
            swap.in_player["player_id"]: data_access.get_average_fixture_difficulty(
                conn, swap.in_player["team_id"], gw, c.DEFAULT_RANKING_HORIZON_GWS
            )
            for swap in top_combo.swaps
        }
        print(f"\nWhy: {rationale.build_rationale(top_combo, fixture_context)}")

        # Captain/vice must come from the squad actually owned right now, not
        # the squad you'd have if you also made the transfer above --
        # recommending a captain you haven't transferred in yet isn't
        # something you can act on.
        squad_ids = {p["player_id"] for p in squad}
        single_gw_projections = {pid: proj_totals.get(pid, {}).get(1, 0.0) for pid in squad_ids}
        players_by_id = {p["player_id"]: p for p in squad}
        players_by_id.update({p["player_id"]: p for p in candidate_pool})

        cap_id, vice_id = captain.recommend_captain(list(squad_ids), single_gw_projections)
        if cap_id is not None:
            cap_name = players_by_id.get(cap_id, {}).get("web_name", f"#{cap_id}")
            cap_team_id = players_by_id.get(cap_id, {}).get("team_id")
            cap_fixture_diff = data_access.get_average_fixture_difficulty(conn, cap_team_id, gw, 1) if cap_team_id else None
            print(f"\nCaptain: {cap_name} ({single_gw_projections[cap_id]:.1f} pts projected GW{gw})")
            print(f"    {rationale.build_captain_rationale(cap_name, single_gw_projections[cap_id], cap_fixture_diff)}")
        if vice_id is not None:
            vice_name = players_by_id.get(vice_id, {}).get("web_name", f"#{vice_id}")
            vice_team_id = players_by_id.get(vice_id, {}).get("team_id")
            vice_fixture_diff = data_access.get_average_fixture_difficulty(conn, vice_team_id, gw, 1) if vice_team_id else None
            print(f"Vice-captain: {vice_name} ({single_gw_projections[vice_id]:.1f} pts projected GW{gw})")
            print(f"    {rationale.build_captain_rationale(vice_name, single_gw_projections[vice_id], vice_fixture_diff)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manager-id", type=int, default=DEFAULT_MANAGER_ID)
    parser.add_argument("--gw", type=int, default=None, help="Gameweek to plan for (default: current/next GW).")
    parser.add_argument("--free-transfers", type=int, default=None, help="Override the reconstructed free-transfer count.")
    parser.add_argument("--no-refresh-squad", dest="refresh_squad", action="store_false", help="Skip pulling a fresh squad snapshot from the API; use the last one stored.")
    parser.add_argument("--no-recompute-projections", dest="recompute_projections", action="store_false", help="Skip recomputing player_projections before ranking transfers.")
    parser.add_argument("--top", type=int, default=5, help="Number of ranked combinations to show.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    run(
        manager_id=args.manager_id,
        gw=args.gw,
        free_transfers_override=args.free_transfers,
        refresh_squad=args.refresh_squad,
        recompute_projections=args.recompute_projections,
        top_n=args.top,
    )


if __name__ == "__main__":
    main()
