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


# Approximate primary shirt colour per club, for the My Squad table's "Kit"
# column -- keyed by the FPL API's 3-letter team short_name. Not official
# branding hex codes, just close enough to be instantly recognizable; any
# short_name not listed here (e.g. a newly promoted club not accounted for)
# falls back to a neutral grey rather than erroring.
TEAM_COLORS = {
    "ARS": ("#EF0107", "white"),
    "AVL": ("#670E36", "white"),
    "BOU": ("#DA291C", "white"),
    "BRE": ("#E30613", "white"),
    "BHA": ("#0057B8", "white"),
    "BUR": ("#6C1D45", "white"),
    "CHE": ("#034694", "white"),
    "CRY": ("#1B458F", "white"),
    "EVE": ("#003399", "white"),
    "FUL": ("#000000", "white"),
    "LEE": ("#FFFFFF", "black"),
    "LIV": ("#C8102E", "white"),
    "MCI": ("#6CABDD", "black"),
    "MUN": ("#DA291C", "white"),
    "NEW": ("#241F20", "white"),
    "NFO": ("#DD0000", "white"),
    "SUN": ("#EB172B", "white"),
    "TOT": ("#132257", "white"),
    "WHU": ("#7A263A", "white"),
    "WOL": ("#FDB913", "black"),
}
DEFAULT_TEAM_COLOR = ("#9E9E9E", "white")


def team_kit_cell_style(kit_value: str) -> str:
    """`kit_value` is expected to be "<shirt emoji> <team short_name>" (see
    `style_kit_column`) -- the team code is pulled from the end of the
    string so this can style the cell using its own displayed text rather
    than needing a second, hidden column."""
    if not kit_value:
        return ""
    team_short = kit_value.rsplit(" ", 1)[-1].upper()
    background, text_color = TEAM_COLORS.get(team_short, DEFAULT_TEAM_COLOR)
    return f"background-color: {background}; color: {text_color}; text-align: center; font-weight: 600"


def style_kit_column(df: pd.DataFrame, kit_column: str = "Kit"):
    """Colors `kit_column` (if present) per the team code embedded in its
    own text -- a lightweight stand-in for an actual shirt graphic, since
    `st.dataframe` cell styling can only color/format text, not render
    arbitrary shapes."""
    if kit_column not in df.columns:
        return df
    return df.style.format(precision=1).map(team_kit_cell_style, subset=[kit_column])
