"""Cell-level styling helpers for dashboard tables. Kept separate from
app.py (which has Streamlit-script side effects like `st.set_page_config()`
at import time) so this pure logic is trivially unit-testable.
"""
import pandas as pd

# Fixture difficulty 1 (easiest) -> 5 (hardest), a ColorBrewer-style
# green-to-red diverging scale with the midpoint swapped for plain grey
# rather than yellow, per the requested "1=strong green ... 3=light grey ...
# 5=strong red" scheme. Text color is chosen per swatch for contrast.
DIFFICULTY_COLORS = {
    1: ("#1a9850", "white"),
    2: ("#91cf60", "black"),
    3: ("#d9d9d9", "black"),
    4: ("#fc8d59", "black"),
    5: ("#d73027", "white"),
}


def difficulty_cell_style(value: str) -> str:
    """A double-gameweek cell ("a/b") is colored by the average of its two
    fixtures' difficulty, rounded to the nearest whole rating -- a blank
    ("-") or unparseable value gets no special styling."""
    if not value or value == "-":
        return ""
    try:
        numbers = [int(part) for part in str(value).split("/")]
    except ValueError:
        return ""
    if not numbers:
        return ""
    rating = round(sum(numbers) / len(numbers))
    rating = min(5, max(1, rating))
    background, text_color = DIFFICULTY_COLORS[rating]
    return f"background-color: {background}; color: {text_color}"


def style_fixture_columns(df: pd.DataFrame, gw_labels: list[str]):
    """Returns a pandas Styler with `difficulty_cell_style` applied to
    whichever of `gw_labels` are actually present as columns in `df` (the
    unmodified DataFrame is returned as-is if none are).

    Also pins float display to 1 decimal place: a bare Styler's default
    float formatting (e.g. "10.400000") is much noisier than the compact
    rendering `st.dataframe` normally gives a plain DataFrame, so without
    this, wrapping a table in a Styler for the color coding would visibly
    regress every other numeric column in it.
    """
    columns_present = [label for label in gw_labels if label in df.columns]
    if not columns_present:
        return df
    return df.style.format(precision=1).map(difficulty_cell_style, subset=columns_present)
