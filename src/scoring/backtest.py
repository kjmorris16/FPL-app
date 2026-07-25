"""Backtest the xPts model against completed historical gameweeks.

For each target gameweek, recomputes projections using only gameweek_stats
data available *before* that gameweek (no look-ahead), then compares the
projected points to what the player actually scored, reporting Pearson
correlation and mean absolute error (MAE) across all (player, gameweek)
pairs in the range.

Requires gameweek_stats to be populated for the range being tested:

    python -m src.ingest.refresh --with-history

Known simplification: team strength ratings (used for clean-sheet
probability) are read from their current snapshot rather than whatever they
were at the time of each historical gameweek. FPL's team strength ratings
move slowly over a season, so this is a minor approximation, not a source of
look-ahead bias in the points themselves.
"""
import argparse
import logging
import math

from src.db import connection
from src.scoring import projections

logger = logging.getLogger(__name__)


def _pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return None
    return covariance / denom


def _mean_absolute_error(xs: list[float], ys: list[float]) -> float | None:
    if not xs:
        return None
    return sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs)


def run_backtest(conn, start_gw: int, end_gw: int) -> tuple[list[tuple], dict]:
    """Returns (pairs, metrics). pairs is a list of (player_id, gw, projected, actual)."""
    pairs = []
    for gw in range(start_gw, end_gw + 1):
        rows = projections.compute_projections(conn, gw, horizon_gws=1, as_of_gw=gw)
        projected_by_player = {r[0]: r[2] for r in rows}

        actual_rows = conn.execute(
            "SELECT player_id, total_points FROM gameweek_stats WHERE gw = ?", (gw,)
        ).fetchall()
        for row in actual_rows:
            projected = projected_by_player.get(row["player_id"])
            if projected is None:
                continue
            pairs.append((row["player_id"], gw, projected, row["total_points"]))

    projected_values = [p[2] for p in pairs]
    actual_values = [p[3] for p in pairs]
    metrics = {
        "n": len(pairs),
        "correlation": _pearson_correlation(projected_values, actual_values),
        "mae": _mean_absolute_error(projected_values, actual_values),
    }
    return pairs, metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-gw", type=int, required=True, help="First completed gameweek to test.")
    parser.add_argument("--end-gw", type=int, required=True, help="Last completed gameweek to test.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    with connection() as conn:
        _, metrics = run_backtest(conn, args.start_gw, args.end_gw)

    print(f"\nBacktest GW{args.start_gw}-GW{args.end_gw}")
    print(f"  Samples:     {metrics['n']}")
    print(f"  Correlation: {metrics['correlation']:.3f}" if metrics["correlation"] is not None else "  Correlation: n/a (insufficient data)")
    print(f"  MAE:         {metrics['mae']:.3f}" if metrics["mae"] is not None else "  MAE:         n/a")


if __name__ == "__main__":
    main()
