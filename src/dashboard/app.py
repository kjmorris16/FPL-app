"""FPL Dashboard -- a single page tying together the squad, transfer
recommendation, chip timing, and mini-league differentials from Phases 1-5.

Run with:
    streamlit run src/dashboard/app.py
"""
import sys
from pathlib import Path

# Streamlit sets sys.path[0] to this file's own directory, not the project
# root, so `import src...` fails unless the repo root is added explicitly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
import streamlit as st

from src.chips import constants as chip_constants
from src.config import DEFAULT_LEAGUE_ID, DEFAULT_MANAGER_ID
from src.dashboard import data as dash_data
from src.dashboard import refresh as dash_refresh
from src.db import init_db
from src.preseason import constants as preseason_constants
from src.scoring.confidence import confidence_label

# A fresh deploy (or a first local run) has no data/fpl.db at all -- data/ is
# gitignored. Without this, every query below would fail with "no such table"
# before the user ever sees the friendly "no data yet" messages further down.
init_db()

POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

st.set_page_config(page_title="FPL Dashboard", page_icon="⚽", layout="wide")
st.title("⚽ FPL Dashboard")

with st.sidebar:
    st.header("Settings")
    manager_id = int(st.number_input("Manager ID", value=DEFAULT_MANAGER_ID, step=1))
    league_id = int(st.number_input("Mini-league ID", value=DEFAULT_LEAGUE_ID, step=1))
    st.caption("Defaults come from `src/config.py` -- override here for a one-off look at a different manager/league.")

    if st.button("🔄 Refresh data", use_container_width=True):
        with st.spinner("Refreshing..."):
            # Stashed in session_state, not shown here directly: st.rerun() below
            # discards anything written in this run before the user sees it, so
            # the message display happens on the *next* run instead.
            st.session_state["refresh_messages"] = dash_refresh.refresh_all(manager_id=manager_id, league_id=league_id)
        st.rerun()

    if st.session_state.get("refresh_messages"):
        for message in st.session_state["refresh_messages"]:
            st.write(message)
        st.session_state["refresh_messages"] = None

current_gw = dash_data.load_current_gw()
st.caption(f"Current gameweek: GW{current_gw}" if current_gw else "No gameweek data yet -- hit Refresh in the sidebar.")

tab_squad, tab_transfers, tab_chips, tab_differentials, tab_preseason = st.tabs(
    ["My Squad", "Transfer Recommendation", "Chip Timing", "Differentials", "Pre-Season Squad"]
)

with tab_squad:
    st.subheader("My Squad")
    squad_section = dash_data.load_squad_section(manager_id)
    if squad_section is None:
        st.info("No squad snapshot yet. Click **Refresh data** in the sidebar to pull your squad from the FPL API.")
    else:
        snapshot = squad_section["snapshot"] or {}
        col1, col2, col3 = st.columns(3)
        col1.metric("Bank", f"£{(snapshot.get('bank') or 0) / 10:.1f}m")
        col2.metric("Free transfers", snapshot.get("free_transfers", "?"))
        col3.metric("Squad value", f"£{(snapshot.get('squad_value') or 0) / 10:.1f}m")

        rows = []
        for p in sorted(squad_section["squad"], key=lambda p: p["squad_position"] or 0):
            role = "C" if p["is_captain"] else ("VC" if p["is_vice_captain"] else "")
            rows.append(
                {
                    "Player": p["web_name"],
                    "Pos": POSITION_NAMES.get(p["element_type"], "?"),
                    "Team": p["team_short"],
                    "Role": role,
                    "Price": f"£{(p['now_cost'] or 0) / 10:.1f}m",
                    f"GW{squad_section['gw']} Proj": round(p["projected_points_gw"], 1),
                    "Recent form": p["recent_form"] or [0],
                }
            )
        st.dataframe(
            pd.DataFrame(rows),
            column_config={"Recent form": st.column_config.BarChartColumn("Recent form (last 6 GWs)", y_min=0)},
            hide_index=True,
            use_container_width=True,
        )

with tab_transfers:
    st.subheader("This Gameweek's Transfer Recommendation")
    rec = dash_data.load_transfer_recommendation(manager_id)
    if rec is None:
        st.info("No transfer recommendation available yet. Make sure your squad snapshot and projections are up to date (hit Refresh).")
    else:
        combo = rec["top_combo"]
        if not combo.swaps:
            st.success("No transfer clears the bar this week -- your current squad is already the strongest option.")
        else:
            for swap in combo.swaps:
                c1, c2, c3 = st.columns(3)
                c1.metric("OUT", swap.out_player["web_name"])
                c2.metric("IN", swap.in_player["web_name"])
                c3.metric("Gain (5 GW)", f"{swap.gains[5]:+.1f}")
            if combo.hit_cost:
                st.warning(f"Costs a -{combo.hit_cost} hit. Net gain (5 GW): {combo.net_gains[5]:+.1f}")
            else:
                st.caption("No hit required -- within your free transfers.")
            st.caption(f"Remaining bank after move: £{combo.remaining_bank / 10:.1f}m")

        st.markdown(f"**Why:** {rec['rationale']}")

        if rec["captain"]:
            cap_col, vice_col = st.columns(2)
            cap_col.metric("Captain", rec["captain"], f"{rec['captain_points']:.1f} pts" if rec["captain_points"] else None)
            if rec["vice_captain"]:
                vice_col.metric("Vice-captain", rec["vice_captain"], f"{rec['vice_captain_points']:.1f} pts" if rec["vice_captain_points"] else None)

        if rec["alternatives"]:
            st.markdown("**Other options considered:**")
            alt_rows = [
                {
                    "Move": ", ".join(f"{s.out_player['web_name']} → {s.in_player['web_name']}" for s in alt.swaps) or "No transfers",
                    "5GW gain": alt.gains[5],
                    "Hit": alt.hit_cost,
                }
                for alt in rec["alternatives"]
            ]
            st.dataframe(pd.DataFrame(alt_rows), hide_index=True, use_container_width=True)

with tab_chips:
    st.subheader("Chip Timing")
    chip_section = dash_data.load_chip_section(manager_id)

    rows = []
    for chip_name, display in chip_constants.CHIP_DISPLAY_NAMES.items():
        info = chip_section["recommendations"][chip_name]
        if not info["available"]:
            rows.append({"Chip": display, "Status": "Used", "Best GW": "-", "Why": ""})
        elif info["best"] is None:
            rows.append({"Chip": display, "Status": "Available", "Best GW": "no signal yet", "Why": ""})
        else:
            rows.append({"Chip": display, "Status": "Available", "Best GW": f"GW{info['best']['gw']}", "Why": info["description"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.markdown("**Season calendar: Bench Boost / Triple Captain value by gameweek**")
    calendar = chip_section["calendar"]
    chart_rows = [
        {"GW": e["gw"], "Bench Boost": e.get("bench_boost_value", 0), "Triple Captain": e.get("triple_captain_value", 0)}
        for e in calendar
    ]
    if chart_rows:
        st.bar_chart(pd.DataFrame(chart_rows).set_index("GW"))

    notes = [f"GW{e['gw']}: {'; '.join(e['notes'])}" for e in calendar if e["notes"]]
    if notes:
        st.markdown("**Fixture swings this window:**")
        for note in notes:
            st.caption(note)

with tab_differentials:
    st.subheader("Mini-League Differentials")
    diff_section = dash_data.load_differentials_section(league_id, manager_id)

    if diff_section.get("league_gw") is None:
        st.info(
            f"No league pick data yet for league {league_id}. Click **Refresh data** -- if this is still the "
            "placeholder league ID, that refresh will fail until your real league exists."
        )
    else:
        players_by_id = diff_section["players_by_id"]
        teams = diff_section["teams"]

        def _diff_rows(rows):
            out = []
            for r in rows:
                player = players_by_id.get(r["player_id"], {})
                gains = r["projected_points"]
                out.append(
                    {
                        "Player": player.get("web_name", f"#{r['player_id']}"),
                        "Team": teams.get(player.get("team_id"), "?"),
                        "1GW": round(gains.get(1, 0.0), 1),
                        "3GW": round(gains.get(3, 0.0), 1),
                        "5GW": round(gains.get(5, 0.0), 1),
                        "Owned %": r["ownership_pct"],
                        "Captained %": r["captaincy_pct"],
                    }
                )
            return out

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Top differentials to consider**")
            st.dataframe(pd.DataFrame(_diff_rows(diff_section["to_transfer_in"])), hide_index=True, use_container_width=True)
        with col2:
            st.markdown("**Differentials you already own**")
            my_rows = _diff_rows(diff_section["my_differentials"])
            if my_rows:
                st.dataframe(pd.DataFrame(my_rows), hide_index=True, use_container_width=True)
            else:
                st.caption("None of your squad qualifies as a differential yet.")

with tab_preseason:
    st.subheader("Pre-Season Squad Selector")
    st.info(
        "Based on last season's data and pre-season signal -- treat as a starting point, "
        "not a certainty, until live data arrives after GW1."
    )

    preseason_budget = st.number_input("Budget (£m)", value=preseason_constants.DEFAULT_BUDGET_TENTHS / 10, step=0.5)
    preseason_section = dash_data.load_preseason_section(budget_tenths=round(preseason_budget * 10))

    if preseason_section is None:
        st.info(
            "No previous-season stats ingested yet. Run `python -m src.ingest.previous_season` "
            "(pulls last season's per-player totals for every current player) first."
        )
    elif "error" in preseason_section:
        st.error(preseason_section["error"])
    else:
        squad = preseason_section["squad"]
        players_by_id = preseason_section["players_by_id"]
        teams = preseason_section["teams"]

        col1, col2 = st.columns(2)
        col1.metric("Squad cost", f"£{preseason_section['total_cost'] / 10:.1f}m")
        col2.metric("Budget", f"£{preseason_section['budget'] / 10:.1f}m")

        def _preseason_row(p):
            info = players_by_id[p["player_id"]]
            return {
                "Player": info["web_name"],
                "Pos": POSITION_NAMES.get(p["element_type"], "?"),
                "Team": teams.get(p["team_id"], "?"),
                "Price": f"£{(p['now_cost'] or 0) / 10:.1f}m",
                "Score": round(p["score"], 1),
                "Confidence": confidence_label(p["confidence"]),
                "Notes": "; ".join(p.get("notes", [])),
            }

        st.markdown("**Suggested 15-man squad**")
        squad_rows = [_preseason_row(p) for p in sorted(squad, key=lambda p: (p["element_type"], -p["score"]))]
        st.dataframe(pd.DataFrame(squad_rows), hide_index=True, use_container_width=True)

        lineup = preseason_section["lineup"]
        st.markdown(f"**Suggested starting XI ({lineup['formation']})**")
        st.dataframe(pd.DataFrame([_preseason_row(p) for p in lineup["starting_xi"]]), hide_index=True, use_container_width=True)

        st.markdown("**Bench**")
        st.dataframe(pd.DataFrame([_preseason_row(p) for p in lineup["bench"]]), hide_index=True, use_container_width=True)

        captain = preseason_section["captain"]
        vice = preseason_section["vice"]
        cap_col, vice_col = st.columns(2)
        cap_col.metric("Captain", players_by_id[captain["player_id"]]["web_name"], f"score {captain['score']:.1f}")
        vice_col.metric("Vice-captain", players_by_id[vice["player_id"]]["web_name"], f"score {vice['score']:.1f}")
        st.caption(
            "Captain/vice picked as the two highest-scoring starting XI players -- same simple rule "
            "Phase 3 uses in-season, just against the pre-season score instead of a live projection."
        )
