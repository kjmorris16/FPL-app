"""Builds a season-long chip calendar and a single top recommendation per
chip, given what a manager still has available.
"""
from src.chips import constants as c, fixture_swings, valuation
from src.transfers import data_access as transfers_data_access

_VALUE_KEY_BY_CHIP = {
    c.CHIP_BENCH_BOOST: "bench_boost_value",
    c.CHIP_TRIPLE_CAPTAIN: "triple_captain_value",
    c.CHIP_WILDCARD: "wildcard_score",
    c.CHIP_FREE_HIT: "free_hit_score",
}


def build_calendar(conn, manager_id: int, start_gw: int, end_gw: int, squad_gw: int | None = None) -> list[dict]:
    """One entry per gameweek in [start_gw, end_gw], with DGW/BGW notes and,
    where a squad snapshot is available, each chip's estimated value that
    week."""
    if squad_gw is None:
        squad_gw = transfers_data_access.get_latest_squad_gw(conn, manager_id)

    teams = {row["id"]: (row["short_name"] or row["name"]) for row in conn.execute("SELECT id, name, short_name FROM teams")}
    dgws = fixture_swings.detect_double_gameweeks(conn, start_gw, end_gw)
    bgws = fixture_swings.detect_blank_gameweeks(conn, start_gw, end_gw)

    calendar = []
    for gw in range(start_gw, end_gw + 1):
        dgw_teams = dgws.get(gw, [])
        bgw_teams = bgws.get(gw, [])

        notes = []
        if dgw_teams:
            notes.append(f"Double gameweek: {', '.join(teams.get(t, f'#{t}') for t in dgw_teams)}")
        if bgw_teams:
            notes.append(f"Blank gameweek: {', '.join(teams.get(t, f'#{t}') for t in bgw_teams)}")

        entry = {"gw": gw, "notes": notes, "dgw_teams": dgw_teams, "bgw_teams": bgw_teams}

        if squad_gw is not None:
            entry["bench_boost_value"] = round(valuation.bench_boost_value(conn, manager_id, squad_gw, gw), 2)
            tc_value, tc_player_id = valuation.triple_captain_value(conn, manager_id, squad_gw, gw)
            entry["triple_captain_value"] = round(tc_value, 2)
            entry["triple_captain_player_id"] = tc_player_id
            entry["free_hit_score"] = valuation.free_hit_window_score(conn, manager_id, squad_gw, gw)

        wc_score, wc_good_run_teams, wc_dgw_teams = valuation.wildcard_window_score(conn, start_gw, end_gw, gw)
        entry["wildcard_score"] = wc_score
        entry["wildcard_good_run_teams"] = sorted(wc_good_run_teams)
        entry["wildcard_dgw_teams"] = sorted(wc_dgw_teams)

        calendar.append(entry)

    return calendar


def _tie_break_key(chip_name: str, entry: dict, key: str):
    """Wildcard ties (e.g. several gameweeks all seeing the same upcoming
    double gameweek within their lookahead window) prefer the *later*
    gameweek -- rebuilding as close as possible to the swing means less time
    with a squad that isn't yet benefiting from it, and more up-to-date team
    news when you do. Every other chip's ties prefer the *earlier* gameweek
    instead, since their values are a rougher guess the further out they are
    (see the module docstring in valuation.py) -- among equally-good weeks,
    the nearer one is the more trustworthy number.
    """
    return (entry[key], entry["gw"] if chip_name == c.CHIP_WILDCARD else -entry["gw"])


def top_recommendation(calendar: list[dict], chip_name: str, available_chips: dict[str, bool]) -> dict | None:
    """Best single gameweek for `chip_name`, or None if it's unavailable or
    the calendar has no signal for it."""
    if not available_chips.get(chip_name, False):
        return None
    key = _VALUE_KEY_BY_CHIP[chip_name]
    candidates = [entry for entry in calendar if entry.get(key) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: _tie_break_key(chip_name, entry, key))


def top_n_gameweeks(calendar: list[dict], chip_name: str, n: int = 3) -> list[dict]:
    key = _VALUE_KEY_BY_CHIP[chip_name]
    candidates = [entry for entry in calendar if entry.get(key) is not None]
    return sorted(candidates, key=lambda entry: _tie_break_key(chip_name, entry, key), reverse=True)[:n]


def describe_recommendation(chip_name: str, entry: dict, teams: dict[int, str] | None = None, players_by_id: dict[int, dict] | None = None) -> str:
    """A one-line plain-English reason for recommending `chip_name` at this
    gameweek's entry."""
    teams = teams or {}
    players_by_id = players_by_id or {}
    gw = entry["gw"]

    if chip_name == c.CHIP_BENCH_BOOST:
        return f"GW{gw}: bench projects {entry['bench_boost_value']:.1f} pts" + (
            f" -- {entry['notes'][0]}" if entry["notes"] else ""
        )
    if chip_name == c.CHIP_TRIPLE_CAPTAIN:
        player_id = entry.get("triple_captain_player_id")
        player_name = players_by_id.get(player_id, {}).get("web_name", f"#{player_id}") if player_id else "your best captain option"
        return f"GW{gw}: tripling {player_name} gains +{entry['triple_captain_value']:.1f} pts over a normal captaincy" + (
            f" -- {entry['notes'][0]}" if entry["notes"] else ""
        )
    if chip_name == c.CHIP_WILDCARD:
        good_run = ", ".join(teams.get(t, f"#{t}") for t in entry.get("wildcard_good_run_teams", []))
        dgw = ", ".join(teams.get(t, f"#{t}") for t in entry.get("wildcard_dgw_teams", []))
        parts = []
        if good_run:
            parts.append(f"{good_run} start good fixture runs next week")
        if dgw:
            parts.append(f"{dgw} have an upcoming double gameweek")
        reason = "; ".join(parts) if parts else "no strong fixture swing detected"
        return f"GW{gw}: rebuild before the fixture picture turns -- {reason}"
    if chip_name == c.CHIP_FREE_HIT:
        return f"GW{gw}: {entry['free_hit_score']} of your squad's players have no fixture" + (
            f" -- {entry['notes'][0]}" if entry["notes"] else ""
        )
    return f"GW{gw}"
