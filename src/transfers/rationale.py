"""Builds a short, deterministic plain-English rationale for the top
recommended transfer combo, from the same signals the optimizer already
computed. No LLM call: this keeps the explanation reproducible, testable,
and directly traceable to the numbers behind it.
"""
from src.transfers import constants as c


def describe_fixture_run(avg_difficulty: float | None) -> str | None:
    if avg_difficulty is None:
        return None
    if avg_difficulty <= 2.4:
        return "a favourable run of fixtures"
    if avg_difficulty <= 3.2:
        return "a middling set of fixtures"
    return "a tough run of fixtures"


def build_rationale(combo, fixture_context: dict[int, float]) -> str:
    """`fixture_context` maps an incoming player's ID to their average fixture
    difficulty over the ranking horizon (see
    `data_access.get_average_fixture_difficulty`)."""
    if not combo.swaps:
        return "Your current squad already projects best over the next few gameweeks -- no transfer clears the bar this week."

    horizon = c.DEFAULT_RANKING_HORIZON_GWS
    sentences = []
    for swap in combo.swaps:
        gain = swap.gains[horizon]
        out_name = swap.out_player["web_name"]
        in_name = swap.in_player["web_name"]
        fixture_desc = describe_fixture_run(fixture_context.get(swap.in_player["player_id"]))

        sentence = f"{in_name} projects {gain:+.1f} more points than {out_name} over the next {horizon} GWs"
        if fixture_desc:
            sentence += f", helped by {fixture_desc}"
        sentences.append(sentence + ".")

    if combo.hit_cost:
        sentences.append(
            f"This costs a -{combo.hit_cost} hit, but the {combo.gains[horizon]:.1f}-point projected gain "
            f"over {horizon} GWs clears that comfortably (net {combo.net_gains[horizon]:+.1f})."
        )
    return " ".join(sentences)


def build_captain_rationale(player_name: str, projected_points: float, fixture_difficulty: float | None) -> str:
    """One-line reasoning for a captain/vice-captain pick. `projected_points`
    is the single-gameweek projection driving the pick -- it already blends
    each player's recent-form and season-long per-90 rates with this week's
    fixture difficulty and their position's scoring model (see
    `scoring.projections`), so this rationale names those factors rather
    than re-deriving them.
    """
    sentence = f"Highest projected points in your current squad this gameweek ({projected_points:.1f}), already weighing recent form and scoring potential"
    fixture_desc = describe_fixture_run(fixture_difficulty)
    if fixture_desc:
        sentence += f" against {fixture_desc}"
    return sentence + "."
