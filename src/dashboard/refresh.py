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
