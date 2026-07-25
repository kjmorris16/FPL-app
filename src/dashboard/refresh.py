"""Manual data refresh triggered from the dashboard's refresh button. Runs
the same ingestion pulls the CLIs use, then clears Streamlit's cache so the
next render picks up fresh data.

Each step is wrapped independently so one failure -- no network access, or
the placeholder mini-league not existing yet -- doesn't block the others.
"""
import logging

import streamlit as st

from src.config import DEFAULT_LEAGUE_ID, DEFAULT_MANAGER_ID
from src.db import connection
from src.differentials import ingestion as differentials_ingestion
from src.ingest import manager as manager_ingest
from src.ingest import previous_season as previous_season_ingest
from src.ingest import refresh as ingest_refresh
from src.scoring import data_access as scoring_data_access, projections as scoring_projections

logger = logging.getLogger(__name__)


def refresh_all(manager_id: int = DEFAULT_MANAGER_ID, league_id: int = DEFAULT_LEAGUE_ID) -> list[str]:
    """Runs every ingestion step, tolerating individual failures. Returns a
    list of human-readable status messages for display in the UI."""
    messages = []

    try:
        ingest_refresh.run(with_history=False)
        messages.append("✅ Players, teams, and fixtures refreshed.")
    except Exception as exc:
        messages.append(f"⚠️ Could not refresh core FPL data: {exc}")

    try:
        with connection() as conn:
            current_gw = scoring_data_access.get_current_gw(conn)
            rows = scoring_projections.compute_projections(conn, start_gw=current_gw, horizon_gws=5)
            scoring_data_access.upsert_projections(conn, rows)
        messages.append("✅ Player projections recomputed.")
    except Exception as exc:
        messages.append(f"⚠️ Could not recompute projections: {exc}")

    try:
        with connection() as conn:
            manager_ingest.fetch_squad_snapshot(conn, manager_id)
        messages.append("✅ Your squad snapshot refreshed.")
    except Exception as exc:
        messages.append(f"⚠️ Could not refresh your squad: {exc}")

    try:
        with connection() as conn:
            manager_ingest.fetch_chip_usage(conn, manager_id)
        messages.append("✅ Your chip usage refreshed.")
    except Exception as exc:
        messages.append(f"⚠️ Could not refresh your chip usage: {exc}")

    try:
        with connection() as conn:
            differentials_ingestion.fetch_league_managers(conn, league_id)
            differentials_ingestion.fetch_league_picks(conn, league_id)
        messages.append(f"✅ League {league_id} managers and picks refreshed.")
    except Exception as exc:
        messages.append(f"⚠️ Could not refresh league {league_id}: {exc}")

    st.cache_data.clear()
    return messages


def refresh_previous_season_stats() -> list[str]:
    """Pulls last season's per-player totals (Phase 8's pre-season selector
    input). Separate from `refresh_all` on purpose: this is one API call per
    player (~700 calls), so it's slow and only needs to run occasionally --
    bundling it into the weekly refresh would make that button dramatically
    slower for no ongoing benefit once the data's already stored. Requires
    the `players` table to already be populated (run the main "Refresh data"
    at least once first).
    """
    messages = []
    try:
        with connection() as conn:
            player_ids = [row["id"] for row in conn.execute("SELECT id FROM players")]
            if not player_ids:
                messages.append("⚠️ No players found yet -- click the main 'Refresh data' button first.")
                return messages
            stored = previous_season_ingest.fetch_previous_season_stats(conn, player_ids)
        messages.append(f"✅ Stored previous-season stats for {stored}/{len(player_ids)} players.")
    except Exception as exc:
        messages.append(f"⚠️ Could not fetch previous-season stats: {exc}")

    st.cache_data.clear()
    return messages
