import pandas as pd

from src.dashboard import styling


def test_difficulty_cell_style_easiest_is_strong_green():
    style = styling.difficulty_cell_style("1")
    assert "#1a9850" in style
    assert "white" in style


def test_difficulty_cell_style_hardest_is_strong_red():
    style = styling.difficulty_cell_style("5")
    assert "#d73027" in style
    assert "white" in style


def test_difficulty_cell_style_middle_is_light_grey():
    style = styling.difficulty_cell_style("3")
    assert "#d9d9d9" in style
    assert "black" in style


def test_difficulty_cell_style_2_and_4_are_softer_shades():
    style_2 = styling.difficulty_cell_style("2")
    style_4 = styling.difficulty_cell_style("4")
    assert "#91cf60" in style_2
    assert "#fc8d59" in style_4


def test_difficulty_cell_style_blank_gameweek_has_no_style():
    assert styling.difficulty_cell_style("-") == ""


def test_difficulty_cell_style_empty_string_has_no_style():
    assert styling.difficulty_cell_style("") == ""


def test_difficulty_cell_style_unparseable_value_has_no_style():
    assert styling.difficulty_cell_style("n/a") == ""


def test_difficulty_cell_style_double_gameweek_uses_average_rounded():
    # (2+4)/2 = 3.0 -> rounds to 3 -> light grey
    style = styling.difficulty_cell_style("2/4")
    assert "#d9d9d9" in style


def test_difficulty_cell_style_double_gameweek_rounds_to_nearest():
    # (1+2)/2 = 1.5 -> Python's round() banker's rounding gives 2
    style = styling.difficulty_cell_style("1/2")
    assert "#91cf60" in style


def test_style_fixture_columns_returns_styler_when_columns_present():
    df = pd.DataFrame({"Player": ["A"], "GW1": ["1"], "GW2": ["5"]})
    result = styling.style_fixture_columns(df, ["GW1", "GW2"])
    assert isinstance(result, pd.io.formats.style.Styler)


def test_style_fixture_columns_returns_plain_df_when_no_columns_present():
    df = pd.DataFrame({"Player": ["A"]})
    result = styling.style_fixture_columns(df, ["GW1", "GW2"])
    assert result is df


def test_style_fixture_columns_applies_correct_colors_to_rendered_html():
    df = pd.DataFrame({"Player": ["A", "B"], "GW1": ["1", "5"]})
    styler = styling.style_fixture_columns(df, ["GW1"])
    html = styler.to_html()
    assert "#1a9850" in html
    assert "#d73027" in html


def test_style_fixture_columns_keeps_float_columns_at_one_decimal():
    """A bare Styler's default float formatting is much noisier (e.g.
    "10.400000") than what a plain st.dataframe would show -- this must not
    regress just because a table now also needs fixture-difficulty colors.
    """
    df = pd.DataFrame({"Player": ["A"], "Score": [10.4], "GW1": ["1"]})
    styler = styling.style_fixture_columns(df, ["GW1"])
    html = styler.to_html()
    assert "10.4" in html
    assert "10.400000" not in html
