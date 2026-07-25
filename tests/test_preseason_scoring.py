from src.preseason import constants as c, scoring


def _insert_team(conn, team_id, name="Team", attack_home=1200, attack_away=1200, defence_home=1200, defence_away=1200):
    conn.execute(
        "INSERT INTO teams (id, name, strength_attack_home, strength_attack_away, strength_defence_home, strength_defence_away) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (team_id, name, attack_home, attack_away, defence_home, defence_away),
    )


def _insert_player(conn, player_id, team_id, element_type, web_name, now_cost=50):
    conn.execute(
        "INSERT INTO players (id, team_id, element_type, web_name, now_cost, status) VALUES (?, ?, ?, ?, ?, 'a')",
        (player_id, team_id, element_type, web_name, now_cost),
    )


def _insert_prev_season(conn, player_id, minutes, expected_goals=0.0, expected_assists=0.0, saves=0, bonus=0):
    conn.execute(
        "INSERT INTO player_previous_season_stats (player_id, season_name, minutes, expected_goals, expected_assists, saves, bonus) "
        "VALUES (?, '2024/25', ?, ?, ?, ?, ?)",
        (player_id, minutes, expected_goals, expected_assists, saves, bonus),
    )


def _insert_fixture(conn, fixture_id, event, team_h, team_a, h_diff=3, a_diff=3):
    conn.execute(
        "INSERT INTO fixtures (id, event, team_h, team_a, team_h_difficulty, team_a_difficulty) VALUES (?, ?, ?, ?, ?, ?)",
        (fixture_id, event, team_h, team_a, h_diff, a_diff),
    )


def test_established_forward_gets_positive_score_and_high_confidence(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_player(db_conn, 101, 1, c.FWD, "Striker")
    _insert_prev_season(db_conn, 101, minutes=3000, expected_goals=18.0, expected_assists=5.0, bonus=15)
    _insert_fixture(db_conn, 1, event=1, team_h=1, team_a=2)
    db_conn.commit()

    scores = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)
    result = scores[101]
    assert result["score"] > 0
    assert result["confidence"] == 1.0  # 3000 >= FULL_CONFIDENCE_MINUTES
    assert result["notes"] == []


def test_player_with_no_history_falls_back_to_position_average(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    # Establish a position average from a couple of proven forwards.
    _insert_player(db_conn, 101, 1, c.FWD, "Established1")
    _insert_player(db_conn, 102, 1, c.FWD, "Established2")
    _insert_prev_season(db_conn, 101, minutes=3000, expected_goals=18.0, expected_assists=3.0)
    _insert_prev_season(db_conn, 102, minutes=2800, expected_goals=14.0, expected_assists=4.0)
    # Brand new signing, no PL history at all.
    _insert_player(db_conn, 103, 1, c.FWD, "NewSigning")
    _insert_fixture(db_conn, 1, event=1, team_h=1, team_a=2)
    db_conn.commit()

    scores = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)
    new_signing = scores[103]

    assert new_signing["score"] > 0  # gets a non-zero projection from the position average
    assert new_signing["confidence"] == c.FALLBACK_CONFIDENCE_NO_HISTORY
    assert c.NO_HISTORY_NOTE in new_signing["notes"]


def test_easier_fixture_scores_higher_than_tougher_one(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_team(db_conn, 3)
    _insert_player(db_conn, 101, 1, c.FWD, "Striker")
    _insert_prev_season(db_conn, 101, minutes=3000, expected_goals=18.0, expected_assists=3.0)
    _insert_fixture(db_conn, 1, event=1, team_h=1, team_a=2, h_diff=2, a_diff=4)  # easy for team 1
    db_conn.commit()
    easy_scores = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)

    db_conn.execute("UPDATE fixtures SET team_h_difficulty = 5, team_a_difficulty = 1 WHERE id = 1")
    db_conn.commit()
    hard_scores = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)

    assert easy_scores[101]["score"] > hard_scores[101]["score"]


def test_goalkeeper_uses_saves_and_outfield_players_do_not(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_player(db_conn, 101, 1, c.GK, "Keeper")
    _insert_prev_season(db_conn, 101, minutes=3400, saves=120)
    _insert_fixture(db_conn, 1, event=1, team_h=1, team_a=2)
    db_conn.commit()

    scores = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)
    assert scores[101]["score"] > 0  # save points contribute


def test_friendly_goal_contribution_adds_small_bonus(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_player(db_conn, 101, 1, c.FWD, "Striker")
    _insert_prev_season(db_conn, 101, minutes=3000, expected_goals=18.0, expected_assists=3.0)
    _insert_fixture(db_conn, 1, event=1, team_h=1, team_a=2)
    db_conn.commit()

    without_friendly = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)[101]["score"]

    db_conn.execute("CREATE TABLE friendly_appearances (player_id INTEGER, minutes INTEGER, goals INTEGER, assists INTEGER)")
    db_conn.execute("INSERT INTO friendly_appearances (player_id, minutes, goals, assists) VALUES (101, 60, 1, 0)")
    db_conn.commit()

    with_friendly = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)[101]
    assert with_friendly["score"] == round(without_friendly + c.FRIENDLY_APPEARANCE_BONUS, 2)
    assert any("friendly" in note.lower() for note in with_friendly["notes"])


def test_established_starter_with_zero_friendly_minutes_flagged_only_when_friendly_data_exists(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_player(db_conn, 101, 1, c.FWD, "Striker")
    _insert_prev_season(db_conn, 101, minutes=3000, expected_goals=18.0, expected_assists=3.0)
    _insert_fixture(db_conn, 1, event=1, team_h=1, team_a=2)
    db_conn.commit()

    # No friendly data ingested at all -- must NOT be flagged (we simply don't know).
    no_friendly_table = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)[101]
    assert no_friendly_table["confidence"] == 1.0
    assert not any("fitness" in note.lower() for note in no_friendly_table["notes"])

    # Friendly data exists for OTHER players, but not this established starter.
    db_conn.execute("CREATE TABLE friendly_appearances (player_id INTEGER, minutes INTEGER, goals INTEGER, assists INTEGER)")
    db_conn.execute("INSERT INTO friendly_appearances (player_id, minutes, goals, assists) VALUES (999, 45, 0, 0)")
    db_conn.commit()

    flagged = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)[101]
    assert flagged["confidence"] <= 0.6
    assert any("fitness" in note.lower() for note in flagged["notes"])


def test_creator_buy_sentiment_gives_small_positive_nudge(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_player(db_conn, 101, 1, c.FWD, "Striker")
    _insert_prev_season(db_conn, 101, minutes=3000, expected_goals=18.0, expected_assists=3.0)
    _insert_fixture(db_conn, 1, event=1, team_h=1, team_a=2)
    db_conn.commit()
    baseline = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)[101]["score"]

    db_conn.execute(
        "CREATE TABLE creator_insights (player_id INTEGER, gameweek INTEGER, sentiment TEXT, reasoning TEXT, creator TEXT)"
    )
    db_conn.execute(
        "INSERT INTO creator_insights (player_id, gameweek, sentiment, reasoning, creator) VALUES (101, 1, 'buy', 'Great pre-season form', 'FPL Raptor')"
    )
    db_conn.commit()

    with_nudge = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)[101]
    assert with_nudge["score"] == round(baseline + c.CREATOR_SENTIMENT_NUDGE, 2)
    assert any("FPL Raptor" in note for note in with_nudge["notes"])


def test_value_per_million_computed(db_conn):
    _insert_team(db_conn, 1)
    _insert_team(db_conn, 2)
    _insert_player(db_conn, 101, 1, c.FWD, "Striker", now_cost=100)
    _insert_prev_season(db_conn, 101, minutes=3000, expected_goals=18.0, expected_assists=3.0)
    _insert_fixture(db_conn, 1, event=1, team_h=1, team_a=2)
    db_conn.commit()

    result = scoring.compute_preseason_scores(db_conn, start_gw=1, horizon_gws=1)[101]
    assert result["value_per_million"] == round(result["score"] / 10.0, 2)
