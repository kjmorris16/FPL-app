"""Cell-level styling helpers for dashboard tables. Kept separate from
app.py (which has Streamlit-script side effects like `st.set_page_config()`
at import time) so this pure logic is trivially unit-testable.
"""
import base64

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
    "ARS": "#EF0107",
    "AVL": "#670E36",
    "BOU": "#DA291C",
    "BRE": "#E30613",
    "BHA": "#0057B8",
    "BUR": "#6C1D45",
    "CHE": "#034694",
    "CRY": "#1B458F",
    "EVE": "#003399",
    "FUL": "#000000",
    "LEE": "#FFFFFF",
    "LIV": "#C8102E",
    "MCI": "#6CABDD",
    "MUN": "#DA291C",
    "NEW": "#241F20",
    "NFO": "#DD0000",
    "SUN": "#EB172B",
    "TOT": "#132257",
    "WHU": "#7A263A",
    "WOL": "#FDB913",
}
DEFAULT_TEAM_COLOR = "#9E9E9E"

# A simple jersey silhouette (collar notch, two sleeves, body) in a 24x24
# viewBox -- filled per-club below rather than relying on the fixed-color
# shirt emoji, which ignores CSS/text color entirely and can only ever
# render its own built-in white/grey. A thin dark outline keeps light kits
# (e.g. all-white) visible against the table's own background.
_SHIRT_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
    '<path fill="{color}" stroke="#00000055" stroke-width="0.75" stroke-linejoin="round" '
    'd="M4 4 L8 2 L10 4 A2 2 0 0 0 14 4 L16 2 L20 4 L18 8 L16 7 L16 20 L8 20 L8 7 L6 8 Z"/>'
    "</svg>"
)


def kit_icon_data_uri(team_short: str) -> str:
    """A small shirt icon filled with `team_short`'s own colour (falling
    back to a neutral grey for an unrecognized code), encoded as a data URI
    for `st.column_config.ImageColumn`. This is what makes the shirt itself
    change colour per team, rather than a fixed-color emoji sat on a
    colored cell background."""
    color = TEAM_COLORS.get((team_short or "").upper(), DEFAULT_TEAM_COLOR)
    svg = _SHIRT_SVG_TEMPLATE.format(color=color)
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
