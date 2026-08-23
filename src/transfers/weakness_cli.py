"""Weekly weak-link check (companion to `src.transfers.cli`): rank the
current squad by weakness_score with each modifier broken out, then print
the best transfer to fix the top weak link (falling back to the next
weakest if it has nothing worth doing).

    python -m src.transfers.weakness_cli
    python -m src.transfers.weakness_cli --gw 12
    python -m src.transfers.weakness_cli --free-transfers 2
    python -m src.transfers.weakness_cli --no-recompute-projections
"""
import argparse
import logging
from datetime import datetime, timezone

from src.config import DEFAULT_MANAGER_ID
from src.db import connection
from src.scoring import data_access as scoring_data_access, projections as scoring_projections
from src.transfers import constants as c, data_access, rationale, weakness

logger = logging.getLogger(__name__)


def _format_price(tenths: int) -> str:
    return f"£{tenths / 10:.1f}m"


def _print_ranking(ranked: list[weakness.WeaknessBreakdown]) -> None:
    print(f"\n{'Rank':<5}{'Player':<16}{'Repl gap':>10}{'Form decl':>11}{'Fix swing':>11}{'Min risk':>10}{'Weakness':>10}")
    for rank, b in enumerate(ranked, start=1):
        print(
            f"{rank:<5}{b.player['web_name']:<16}{b.replacement_gap:>10.2f}{b.form_decline:>11.2f}"
            f"{b.fixture_swing:>11.2f}{b.minutes_risk:>10.2f}{b.weakness_score:>10.2f}"
        )


def run(
    manager_id: int = DEFAULT_MANAGER_ID,
    gw: int | None = None,
    free_transfers_override: int | None = None,
    recompute_projections: bool = True,
) -> None:
    with connection() as conn:
        gw = gw or data_access.get_latest_squad_gw(conn, manager_id)
        if gw is None:
            raise RuntimeError(
                f"No squad snapshot found for manager {manager_id}. Run `python -m src.transfers.cli` first."
            )

        if recompute_projections:
            rows = scoring_projections.compute_projections(conn, start_gw=gw, horizon_gws=c.WEAKNESS_HORIZON_GWS)
            scoring_data_access.upsert_projections(conn, rows)

        manager_snapshot = data_access.get_manager_snapshot(conn, manager_id, gw)
        if manager_snapshot is None:
            raise RuntimeError(f"No manager snapshot for GW{gw} -- run `python -m src.transfers.cli` first.")

        bank = manager_snapshot["bank"]
        free_transfers = free_transfers_override if free_transfers_override is not None else manager_snapshot["free_transfers"]

        squad = data_access.get_current_squad(conn, manager_id, gw)
        candidate_pool = data_access.get_candidate_pool(conn)
        all_ids = {p["player_id"] for p in squad} | {p["player_id"] for p in candidate_pool}
        projections = data_access.get_projection_totals(
            conn, list(all_ids), start_gw=gw, horizons=(c.WEAKNESS_HORIZON_GWS,)
        )
        histories = scoring_data_access.get_all_player_histories(conn)

        ranked = weakness.rank_squad_weakness(conn, squad, candidate_pool, projections, histories, current_gw=gw)

        computed_at = datetime.now(timezone.utc).isoformat()
        data_access.upsert_squad_weakness(conn, weakness.to_storage_rows(manager_id, gw, ranked, computed_at))

        print(f"\nSquad weakness ranking for GW{gw} (manager {manager_id})")
        _print_ranking(ranked)

        recommendation = weakness.recommend_weak_link_transfer(ranked, squad, candidate_pool, bank, free_transfers, projections)
        if recommendation is None:
            print("\nNo transfer among the weakest players clears the bar this week.")
            return

        weak_link_name = recommendation.weak_link.player["web_name"]
        in_name = recommendation.replacement["web_name"]
        fixture_diff = data_access.get_average_fixture_difficulty(
            conn, recommendation.replacement["team_id"], gw, c.WEAKNESS_HORIZON_GWS
        )

        print(f"\nRecommended: OUT {weak_link_name} -> IN {in_name}")
        print(f"    {rationale.build_weak_link_flagged_reason(weak_link_name, recommendation.weak_link_reason)}")
        print(
            "    "
            + rationale.build_weak_link_replacement_reason(
                weak_link_name, recommendation.replacement, recommendation.net_gain,
                c.WEAKNESS_HORIZON_GWS, fixture_diff, recommendation.hit_cost,
            )
        )
        if recommendation.hit_cost:
            print(f"    Costs a -{recommendation.hit_cost} hit.")
        print(f"    Remaining bank: {_format_price(bank - recommendation.cost_delta)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manager-id", type=int, default=DEFAULT_MANAGER_ID)
    parser.add_argument("--gw", type=int, default=None, help="Gameweek to check (default: your latest saved squad).")
    parser.add_argument("--free-transfers", type=int, default=None, help="Override the reconstructed free-transfer count.")
    parser.add_argument("--no-recompute-projections", dest="recompute_projections", action="store_false", help="Skip recomputing player_projections before ranking.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    run(
        manager_id=args.manager_id,
        gw=args.gw,
        free_transfers_override=args.free_transfers,
        recompute_projections=args.recompute_projections,
    )


if __name__ == "__main__":
    main()
