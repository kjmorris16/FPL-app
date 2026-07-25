"""Pull a manager's live squad, bank, and free transfers from the FPL API and
store a snapshot so squad changes can be tracked over the season.

The public FPL API has no login-gated "my team" endpoint with exact sell
prices, so this reconstructs them from public data:
  - `entry/{id}/transfers/` gives the price paid (`element_in_cost`) for every
    player ever transferred in, which lets us derive a sell price using FPL's
    real rule (keep half the profit, rounded down; eat the full loss).
  - A squad player who has never appeared as a transfer-in this season (still
    holding their original gameweek-1 pick) has no recorded purchase price in
    the public API. We fall back to their current price for those players,
    i.e. assume zero banked profit. This can modestly understate available
    budget for long-held risers -- a conservative bias, not a reckless one.

Free transfers available aren't returned directly either, so they're
simulated forward from `entry/{id}/history/`'s per-gameweek transfer counts
and costs (a transfer's cost is always a multiple of -4, so hits taken =
cost / 4), skipping any gameweek a Wildcard or Free Hit chip was played
(chip gameweeks don't touch the free-transfer counter). This is a best-effort
reconstruction of FPL's rollover rule (max 5 banked) -- if it ever drifts from
what the FPL app shows you, override it with `--free-transfers` on the CLI.
"""
import logging
from datetime import datetime, timezone

from src.ingest import api_client

logger = logging.getLogger(__name__)

STARTING_FREE_TRANSFERS = 1
MAX_FREE_TRANSFERS = 5
CHIP_NAMES_RESETTING_TRANSFER_COUNT = {"wildcard", "freehit", "free_hit"}


def compute_sell_price(purchase_price: int, current_price: int) -> int:
    """FPL's actual sell-price rule: keep half of any profit (rounded down),
    eat the full loss if the price has fallen."""
    if current_price <= purchase_price:
        return current_price
    profit = current_price - purchase_price
    return purchase_price + profit // 2


def reconstruct_purchase_prices(transfers: list[dict]) -> dict[int, int]:
    """player_id -> price paid (tenths of a million), using the most recent
    transfer-in for each player (handles sold-then-rebought players)."""
    purchase_price = {}
    for t in sorted(transfers, key=lambda t: (t.get("event") or 0, t.get("time") or "")):
        purchase_price[t["element_in"]] = t["element_in_cost"]
    return purchase_price


def compute_free_transfers(history_current: list[dict], chips: list[dict], upcoming_gw: int) -> int:
    """Simulate free-transfer accumulation up to (not including) `upcoming_gw`."""
    chip_events = {c["event"] for c in chips if c.get("name") in CHIP_NAMES_RESETTING_TRANSFER_COUNT}

    ft = STARTING_FREE_TRANSFERS  # available entering GW2; GW1 has no FT concept
    for row in sorted(history_current, key=lambda r: r["event"]):
        gw = row["event"]
        if gw < 2 or gw >= upcoming_gw:
            continue
        if gw in chip_events:
            ft = min(MAX_FREE_TRANSFERS, ft + 1)
            continue
        transfers_made = row.get("event_transfers") or 0
        hits_taken = abs(row.get("event_transfers_cost") or 0) // 4
        free_used = min(max(0, transfers_made - hits_taken), ft)
        ft = min(MAX_FREE_TRANSFERS, ft - free_used + 1)
    return max(1, min(MAX_FREE_TRANSFERS, ft))


def _fetch_picks_with_fallback(manager_id: int, gw: int, min_gw: int = 1) -> tuple[int, dict]:
    """Try `gw`'s picks, falling back to earlier gameweeks if it 404s (e.g. the
    upcoming gameweek's squad hasn't been "saved" as a distinct picks record
    yet)."""
    try:
        return gw, api_client.get_entry_picks(manager_id, gw)
    except RuntimeError:
        if gw > min_gw:
            return _fetch_picks_with_fallback(manager_id, gw - 1, min_gw)
        raise


def fetch_squad_snapshot(conn, manager_id: int, gw: int | None = None) -> dict:
    """Pull the manager's current squad/bank/free-transfers from the FPL API,
    store a snapshot in `my_manager_snapshot` / `my_squad_history`, and return
    it as a plain dict for immediate use by the optimizer.
    """
    from src.scoring import data_access as scoring_data_access

    if gw is None:
        gw = scoring_data_access.get_current_gw(conn)

    picks_gw, picks_payload = _fetch_picks_with_fallback(manager_id, gw)
    history = api_client.get_entry_history(manager_id)
    transfers = api_client.get_entry_transfers(manager_id)

    purchase_prices = reconstruct_purchase_prices(transfers)
    free_transfers = compute_free_transfers(history.get("current", []), history.get("chips", []), gw)

    entry_history = picks_payload.get("entry_history", {})
    bank = entry_history.get("bank", 0)
    squad_value = entry_history.get("value", 0)

    now_costs = {row["id"]: row["now_cost"] for row in conn.execute("SELECT id, now_cost FROM players")}

    squad = []
    for pick in picks_payload.get("picks", []):
        player_id = pick["element"]
        current_price = now_costs.get(player_id, 0)
        purchase_price = purchase_prices.get(player_id, current_price)
        sell_price = compute_sell_price(purchase_price, current_price)
        squad.append(
            {
                "player_id": player_id,
                "squad_position": pick.get("position"),
                "is_captain": bool(pick.get("is_captain")),
                "is_vice_captain": bool(pick.get("is_vice_captain")),
                "multiplier": pick.get("multiplier"),
                "purchase_price": purchase_price,
                "sell_price": sell_price,
            }
        )

    pulled_at = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        INSERT INTO my_manager_snapshot (manager_id, gw, bank, squad_value, free_transfers, pulled_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(manager_id, gw) DO UPDATE SET
            bank=excluded.bank, squad_value=excluded.squad_value,
            free_transfers=excluded.free_transfers, pulled_at=excluded.pulled_at
        """,
        (manager_id, gw, bank, squad_value, free_transfers, pulled_at),
    )
    conn.executemany(
        """
        INSERT INTO my_squad_history (
            manager_id, gw, player_id, squad_position, is_captain, is_vice_captain,
            multiplier, purchase_price, sell_price, pulled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(manager_id, gw, player_id) DO UPDATE SET
            squad_position=excluded.squad_position, is_captain=excluded.is_captain,
            is_vice_captain=excluded.is_vice_captain, multiplier=excluded.multiplier,
            purchase_price=excluded.purchase_price, sell_price=excluded.sell_price,
            pulled_at=excluded.pulled_at
        """,
        [
            (
                manager_id, gw, s["player_id"], s["squad_position"], int(s["is_captain"]),
                int(s["is_vice_captain"]), s["multiplier"], s["purchase_price"], s["sell_price"], pulled_at,
            )
            for s in squad
        ],
    )

    logger.info(
        "Stored squad snapshot for manager %d, GW%d (picks from GW%d): bank=%.1f, FT=%d",
        manager_id, gw, picks_gw, bank / 10, free_transfers,
    )

    return {
        "gw": gw,
        "picks_gw": picks_gw,
        "bank": bank,
        "squad_value": squad_value,
        "free_transfers": free_transfers,
        "squad": squad,
    }
