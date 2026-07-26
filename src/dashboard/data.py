"""Data-loading helpers for the Streamlit dashboard. Wraps the phase modules
so app.py stays focused on layout.

Every loader opens its own short-lived DB connection and is wrapped in
`st.cache_data` so Streamlit's rerun-on-every-interaction model doesn't
recompute everything (projections, transfer combos, differential ranking) on
every widget click. The "Refresh data" button (`src/dashboard/refresh.py`) is
the only thing that hits the network; it explicitly clears this cache
afterwards so the next render picks up what it just pulled.
"""
import streamlit as st

from src.chips import availability as chip_availability, constants as chip_constants, planner as chip_planner
from src.db import connection
from src.differentials import data_access as diff_data_access, finder as diff_finder
from src.preseason import constants as preseason_constants, data_access as preseason_data_access, optimizer as preseason_optimizer, scoring as preseason_scoring
from src.scoring import data_access as scoring_data_access
from src.transfers import captain as transfer_captain, constants as transfer_constants, data_access as transfers_data_access, optimizer, rationale

CACHE_TTL_SECONDS = 60


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_current_gw() -> int | None:
    with connection() as conn:
        try:
            return scoring_data_access.get_current_gw(conn)
        except Exception:
            return None


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_squad_section(manager_id: int) -> dict | None:
    with connection() as conn:
        gw = transfers_data_access.get_latest_squad_gw(conn, manager_id)
        if gw is None:
            return None

        snapshot = transfers_data_access.get_manager_snapshot(conn, manager_id, gw)
        squad = transfers_data_access.get_current_squad(conn, manager_id, gw)
        player_ids = [p["player_id"] for p in squad]

        totals = transfers_data_access.get_projection_totals(conn, player_ids, start_gw=gw, horizons=(1,)) if player_ids else {}

        history_by_player: dict[int, list] = {}
        if player_ids:
            placeholders = ",".join("?" for _ in player_ids)
            rows = conn.execute(
                f"SELECT player_id, gw, total_points FROM gameweek_stats WHERE player_id IN ({placeholders}) ORDER BY player_id, gw",
                player_ids,
            ).fetchall()
            for row in rows:
                history_by_player.setdefault(row["player_id"], []).append(row["total_points"] or 0)

        teams = {row["id"]: (row["short_name"] or row["name"]) for row in conn.execute("SELECT id, name, short_name FROM teams")}

    for p in squad:
        p["projected_points_gw"] = totals.get(p["player_id"], {}).get(1, 0.0)
        p["recent_form"] = history_by_player.get(p["player_id"], [])[-6:]
        p["team_short"] = teams.get(p["team_id"], "?")

    return {"gw": gw, "snapshot": snapshot, "squad": squad}


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_transfer_recommendation(manager_id: int) -> dict | None:
    with connection() as conn:
        gw = transfers_data_access.get_latest_squad_gw(conn, manager_id)
        if gw is None:
            return None

        manager_snapshot = transfers_data_access.get_manager_snapshot(conn, manager_id, gw)
        if manager_snapshot is None:
            return None

        squad = transfers_data_access.get_current_squad(conn, manager_id, gw)
        candidate_pool = transfers_data_access.get_candidate_pool(conn)
        all_ids = {p["player_id"] for p in squad} | {p["player_id"] for p in candidate_pool}
        proj_totals = transfers_data_access.get_projection_totals(
            conn, list(all_ids), start_gw=gw, horizons=transfer_constants.REPORTED_HORIZONS_GWS
        )

        combos = optimizer.generate_combos(squad, candidate_pool, manager_snapshot["bank"], manager_snapshot["free_transfers"], proj_totals)
        if not combos:
            return None
        top_combo = combos[0]

        fixture_context = {
            swap.in_player["player_id"]: transfers_data_access.get_average_fixture_difficulty(
                conn, swap.in_player["team_id"], gw, transfer_constants.DEFAULT_RANKING_HORIZON_GWS
            )
            for swap in top_combo.swaps
        }
        rationale_text = rationale.build_rationale(top_combo, fixture_context)

        squad_ids = {p["player_id"] for p in squad}
        out_ids = {s.out_player["player_id"] for s in top_combo.swaps}
        in_ids = {s.in_player["player_id"] for s in top_combo.swaps}
        resulting_squad_ids = (squad_ids - out_ids) | in_ids
        single_gw_projections = {pid: proj_totals.get(pid, {}).get(1, 0.0) for pid in resulting_squad_ids}
        players_by_id = {p["player_id"]: p for p in squad}
        players_by_id.update({p["player_id"]: p for p in candidate_pool})
        cap_id, vice_id = transfer_captain.recommend_captain(list(resulting_squad_ids), single_gw_projections)

    return {
        "gw": gw,
        "bank": manager_snapshot["bank"],
        "free_transfers": manager_snapshot["free_transfers"],
        "top_combo": top_combo,
        "alternatives": combos[1:4],
        "rationale": rationale_text,
        "captain": players_by_id.get(cap_id, {}).get("web_name") if cap_id else None,
        "captain_points": single_gw_projections.get(cap_id) if cap_id else None,
        "vice_captain": players_by_id.get(vice_id, {}).get("web_name") if vice_id else None,
        "vice_captain_points": single_gw_projections.get(vice_id) if vice_id else None,
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_chip_section(manager_id: int, horizon_gws: int = chip_constants.PLANNING_HORIZON_GWS) -> dict:
    with connection() as conn:
        current_gw = scoring_data_access.get_current_gw(conn)
        end_gw = current_gw + horizon_gws - 1

        chip_usage = [
            dict(row) for row in conn.execute("SELECT chip_name, event FROM chip_usage WHERE manager_id = ?", (manager_id,))
        ]
        available = chip_availability.get_available_chips(chip_usage, current_gw)

        squad_gw = transfers_data_access.get_latest_squad_gw(conn, manager_id)
        calendar = chip_planner.build_calendar(conn, manager_id, current_gw, end_gw, squad_gw=squad_gw)

        teams = {row["id"]: (row["short_name"] or row["name"]) for row in conn.execute("SELECT id, name, short_name FROM teams")}
        players_by_id = {row["id"]: dict(row) for row in conn.execute("SELECT id, web_name FROM players")}

    recommendations = {}
    for chip_name in chip_constants.CHIP_DISPLAY_NAMES:
        best = chip_planner.top_recommendation(calendar, chip_name, available)
        recommendations[chip_name] = {
            "available": available.get(chip_name, False),
            "best": best,
            "description": chip_planner.describe_recommendation(chip_name, best, teams=teams, players_by_id=players_by_id) if best else None,
        }

    return {
        "current_gw": current_gw,
        "end_gw": end_gw,
        "calendar": calendar,
        "recommendations": recommendations,
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_differentials_section(league_id: int, manager_id: int, top_n: int = 10, max_ownership_pct: float = 30.0) -> dict:
    with connection() as conn:
        current_gw = scoring_data_access.get_current_gw(conn)
        league_gw = diff_data_access.get_latest_league_picks_gw(conn, league_id)
        if league_gw is None:
            return {"league_gw": None}

        my_squad_gw = transfers_data_access.get_latest_squad_gw(conn, manager_id)

        to_transfer_in = diff_finder.rank_differentials_to_transfer_in(
            conn, league_id, manager_id, league_gw, my_squad_gw, start_gw=current_gw, top_n=top_n, max_ownership_pct=max_ownership_pct,
        )
        my_differentials = diff_finder.rank_my_differentials(
            conn, league_id, manager_id, league_gw, my_squad_gw, start_gw=current_gw, top_n=top_n, max_ownership_pct=max_ownership_pct,
        )
        players_by_id = {row["id"]: dict(row) for row in conn.execute("SELECT id, web_name, team_id FROM players")}
        teams = {row["id"]: (row["short_name"] or row["name"]) for row in conn.execute("SELECT id, name, short_name FROM teams")}

    return {
        "league_gw": league_gw,
        "to_transfer_in": to_transfer_in,
        "my_differentials": my_differentials,
        "players_by_id": players_by_id,
        "teams": teams,
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_preseason_coverage() -> dict:
    """How many current players have previous-season stats stored, so a data
    problem (e.g. the fetch silently storing 0 rows) is visible at a glance
    rather than only showing up as every player scoring 0."""
    with connection() as conn:
        total_players = conn.execute("SELECT COUNT(*) AS n FROM players").fetchone()["n"]
        players_with_stats = conn.execute("SELECT COUNT(*) AS n FROM player_previous_season_stats").fetchone()["n"]
    return {"total_players": total_players, "players_with_stats": players_with_stats}


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_fixture_ticker(start_gw: int = preseason_constants.START_GW, num_gws: int = preseason_constants.FIXTURE_TICKER_GWS) -> dict[int, list[str]]:
    """team_id -> list of per-gameweek fixture difficulty labels."""
    with connection() as conn:
        return preseason_data_access.get_team_fixture_ticker(conn, start_gw, num_gws)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_player_directory() -> dict[int, dict]:
    """All current players' id -> {web_name, element_type, team_name}, for
    UI widgets (search/select) that don't need full pre-season scoring."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT p.id, p.web_name, p.element_type, COALESCE(t.short_name, t.name) AS team_name "
            "FROM players p LEFT JOIN teams t ON t.id = p.team_id"
        ).fetchall()
    return {row["id"]: dict(row) for row in rows}


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_preseason_section(
    budget_tenths: int = preseason_constants.DEFAULT_BUDGET_TENTHS,
    horizon_gws: int = preseason_constants.FIXTURE_HORIZON_GWS,
    must_include_ids: tuple = (),
    must_exclude_ids: tuple = (),
) -> dict | None:
    """None if no previous-season stats have been ingested yet; a dict with an
    "error" key if a full 15-man squad can't be built within budget (this
    includes contradictory must-include/must-exclude requests).

    `must_include_ids`/`must_exclude_ids` are tuples (not sets) so this stays
    hashable for st.cache_data.
    """
    with connection() as conn:
        scores = preseason_scoring.compute_preseason_scores(conn, start_gw=preseason_constants.START_GW, horizon_gws=horizon_gws)
        if not scores:
            return None
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

    try:
        squad = preseason_optimizer.select_best_squad(
            candidates, budget=budget_tenths,
            must_include_ids=set(must_include_ids), must_exclude_ids=set(must_exclude_ids),
        )
    except RuntimeError as exc:
        return {"error": str(exc)}

    total_score = sum(p["score"] for p in squad)
    if must_include_ids or must_exclude_ids:
        # Only worth a second solve when there's actually a constraint that
        # could make this squad worse than the unconstrained optimum --
        # otherwise `squad` already *is* that optimum.
        baseline_squad = preseason_optimizer.select_best_squad(candidates, budget=budget_tenths)
        baseline_score = sum(p["score"] for p in baseline_squad)
    else:
        baseline_score = total_score

    lineup = preseason_optimizer.select_starting_xi(squad)
    ranked_xi = sorted(lineup["starting_xi"], key=lambda p: p["score"], reverse=True)

    return {
        "squad": squad,
        "lineup": lineup,
        "players_by_id": players_by_id,
        "teams": teams,
        "captain": ranked_xi[0],
        "vice": ranked_xi[1],
        "total_cost": sum(p["now_cost"] for p in squad),
        "total_score": round(total_score, 1),
        "score_pct": preseason_optimizer.score_percentage(total_score, baseline_score),
        "budget": budget_tenths,
    }
