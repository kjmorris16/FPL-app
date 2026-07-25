"""Pre-season expected-points scoring: last season's per-90 rates (shrunk
towards position averages by last-season minutes, the same shrinkage
estimator Phase 2 uses for new signings) projected across the opening
fixture window, using the exact same points model, clean-sheet model, and
fixture-difficulty adjustments Phase 2 uses for in-season projections --
just fed last-season rates instead of blended current-season ones, since
`gameweek_stats` is entirely empty before GW1.

Friendly-appearance and creator-insight signals are intentionally small,
additive nudges layered on top afterwards -- never large enough to override
the season-long underlying-stats signal that actually drives the score.
"""
from src.preseason import constants as c
from src.preseason import data_access as preseason_data_access
from src.scoring import adjustments, clean_sheets, confidence as confidence_module, points_model
from src.scoring import data_access as scoring_data_access
from src.scoring import underlying
from src.transfers import data_access as transfers_data_access


def _per90(total_stat, total_minutes: int) -> float:
    if not total_minutes:
        return 0.0
    return (total_stat or 0) / total_minutes * 90


def _position_average_rates(players: list[dict], prev_stats: dict[int, dict]) -> dict[int, dict[str, float]]:
    """element_type -> {xg90, xa90, saves90, bonus90, minutes_share} league
    averages, from players with enough last-season minutes to be reliable."""
    buckets = {
        et: {"xg90": [], "xa90": [], "saves90": [], "bonus90": [], "minutes_share": []}
        for et in c.SQUAD_COMPOSITION
    }
    for player in players:
        stats = prev_stats.get(player["player_id"])
        if not stats or (stats.get("minutes") or 0) < c.SHRINKAGE_FULL_WEIGHT_MINUTES:
            continue
        et = player["element_type"]
        if et not in buckets:
            continue
        minutes = stats["minutes"]
        buckets[et]["xg90"].append(_per90(stats.get("expected_goals"), minutes))
        buckets[et]["xa90"].append(_per90(stats.get("expected_assists"), minutes))
        buckets[et]["saves90"].append(_per90(stats.get("saves"), minutes))
        buckets[et]["bonus90"].append(_per90(stats.get("bonus"), minutes))
        buckets[et]["minutes_share"].append(min(1.0, minutes / c.FULL_SEASON_MINUTES))

    return {
        et: {key: (sum(values) / len(values) if values else 0.0) for key, values in rates.items()}
        for et, rates in buckets.items()
    }


def _shrunk_rate(raw_rate: float | None, minutes_last: int, position_avg_rate: float) -> float:
    return underlying.shrink_to_position_average(
        raw_rate, minutes_last, position_avg_rate, full_confidence_minutes=c.SHRINKAGE_FULL_WEIGHT_MINUTES
    )


def _score_player(
    player: dict,
    stats_row: dict | None,
    team: dict,
    teams: dict[int, dict],
    league_avgs: dict,
    pos_avg: dict,
    fixtures_by_team_gw: dict,
    start_gw: int,
    horizon_gws: int,
    friendly_row: dict | None,
    has_any_friendly_data: bool,
    creator_notes: list[dict],
) -> dict:
    element_type = player["element_type"]
    pos_rates = pos_avg[element_type]
    has_history = stats_row is not None
    minutes_last = (stats_row or {}).get("minutes") or 0

    raw_minutes_share = min(1.0, minutes_last / c.FULL_SEASON_MINUTES) if has_history else None
    minutes_share = _shrunk_rate(raw_minutes_share, minutes_last, pos_rates["minutes_share"])

    raw_xg90 = _per90(stats_row.get("expected_goals"), minutes_last) if has_history else None
    raw_xa90 = _per90(stats_row.get("expected_assists"), minutes_last) if has_history else None
    raw_bonus90 = _per90(stats_row.get("bonus"), minutes_last) if has_history else None
    xg90 = _shrunk_rate(raw_xg90, minutes_last, pos_rates["xg90"])
    xa90 = _shrunk_rate(raw_xa90, minutes_last, pos_rates["xa90"])
    bonus90 = _shrunk_rate(raw_bonus90, minutes_last, pos_rates["bonus90"])
    saves90 = 0.0
    if element_type == c.GK:
        raw_saves90 = _per90(stats_row.get("saves"), minutes_last) if has_history else None
        saves90 = _shrunk_rate(raw_saves90, minutes_last, pos_rates["saves90"])

    total_points = 0.0
    team_fixtures = fixtures_by_team_gw.get(player["team_id"], {})
    for gw in range(start_gw, start_gw + horizon_gws):
        for fixture in team_fixtures.get(gw, []):
            opponent = teams.get(fixture["opponent_team"], {})
            difficulty = fixture["difficulty"] or 3
            atk_mult = adjustments.attacking_multiplier(difficulty)
            def_mult = adjustments.defensive_shots_multiplier(difficulty)
            exp_conceded = clean_sheets.expected_goals_conceded(team, opponent, fixture["is_home"], league_avgs)
            cs_prob = clean_sheets.clean_sheet_probability(exp_conceded)
            total_points += points_model.fixture_points(
                element_type, p60=minutes_share, p_short=0.0, exp_minutes=minutes_share * 90,
                xg90=xg90, xa90=xa90, saves90=saves90, clean_sheet_prob=cs_prob,
                expected_goals_conceded=exp_conceded, atk_multiplier=atk_mult, def_multiplier=def_mult, bonus90=bonus90,
            )

    conf = confidence_module.confidence_score(minutes_last, c.FULL_CONFIDENCE_MINUTES, c.FALLBACK_CONFIDENCE_NO_HISTORY)

    notes = []
    if not has_history:
        notes.append(c.NO_HISTORY_NOTE)

    if friendly_row and ((friendly_row.get("goals") or 0) + (friendly_row.get("assists") or 0) > 0):
        total_points += c.FRIENDLY_APPEARANCE_BONUS
        notes.append("Contributed a goal/assist in a recorded pre-season friendly.")
    elif has_any_friendly_data and has_history and minutes_last >= c.NAILED_LAST_SEASON_MINUTES and not friendly_row:
        conf = min(conf, 0.6)
        notes.append("Established starter with no recorded pre-season minutes -- possible fitness/rotation concern.")

    for note in creator_notes:
        sentiment = (note.get("sentiment") or "").lower()
        if sentiment in ("buy", "captain"):
            total_points += c.CREATOR_SENTIMENT_NUDGE
        elif sentiment in ("sell", "avoid"):
            total_points -= c.CREATOR_SENTIMENT_NUDGE
        creator = note.get("creator") or "a creator"
        reasoning = note.get("reasoning") or ""
        notes.append(f"{creator} ({sentiment}): {reasoning}".strip())

    value_per_million = round(total_points / (player["now_cost"] / 10), 2) if player.get("now_cost") else 0.0

    return {
        "player_id": player["player_id"],
        "score": round(total_points, 2),
        "confidence": round(conf, 3),
        "value_per_million": value_per_million,
        "notes": notes,
    }


def compute_preseason_scores(conn, start_gw: int = c.START_GW, horizon_gws: int = c.FIXTURE_HORIZON_GWS) -> dict[int, dict]:
    """Returns {player_id: {score, confidence, value_per_million, notes}} for
    every current player, projected across [start_gw, start_gw + horizon_gws - 1]."""
    players = transfers_data_access.get_candidate_pool(conn)
    teams = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM teams")}
    league_avgs = clean_sheets.league_strength_averages(teams.values())
    prev_stats = preseason_data_access.get_previous_season_stats(conn)
    pos_avg = _position_average_rates(players, prev_stats)
    fixtures_by_team_gw = scoring_data_access.get_team_fixtures_map(conn, start_gw, start_gw + horizon_gws - 1)
    friendly_summary = preseason_data_access.get_friendly_appearances_summary(conn)
    has_any_friendly_data = bool(friendly_summary)
    creator_notes_by_player = preseason_data_access.get_preseason_creator_notes(conn, target_gw=start_gw)

    scores = {}
    for player in players:
        team = teams.get(player["team_id"])
        if team is None:
            continue
        scores[player["player_id"]] = _score_player(
            player,
            prev_stats.get(player["player_id"]),
            team,
            teams,
            league_avgs,
            pos_avg,
            fixtures_by_team_gw,
            start_gw,
            horizon_gws,
            friendly_summary.get(player["player_id"]),
            has_any_friendly_data,
            creator_notes_by_player.get(player["player_id"], []),
        )
    return scores
