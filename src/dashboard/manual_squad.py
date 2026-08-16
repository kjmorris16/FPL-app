"""Support for manually entering a squad in the dashboard's My Squad tab --
needed pre-season, when the FPL API has no saved picks yet to pull
(`src.ingest.manager.fetch_squad_snapshot` needs a real picks record, which
doesn't exist until GW1's deadline passes).
"""
from difflib import SequenceMatcher

from src.scoring.constants import DEF, FWD, GK, MID

# A starting point for the manual-entry table, pre-filled from a squad
# screenshot the user provided (name, expected position, role). Purely a
# convenience default -- every row is still a normal editable dropdown, so a
# wrong guess (e.g. an ambiguous surname shared by two players) is a
# one-click fix, not something this needs to get perfectly right.
SUGGESTED_SQUAD_HINTS = [
    ("Kinsky", GK, ""),
    ("Hincapie", DEF, ""),
    ("N.Williams", DEF, ""),
    ("Jacquet", DEF, ""),
    ("Maguire", DEF, ""),
    ("B.Fernandes", MID, "C"),
    ("Szoboszlai", MID, ""),
    ("Le Fée", MID, ""),
    ("Solanke", FWD, ""),
    ("Haaland", FWD, "VC"),
    ("João Pedro", FWD, ""),
    ("Palmer", GK, ""),
    ("Sarr", MID, ""),
    ("Ndiaye", MID, ""),
    ("van Ewijk", DEF, ""),
]

MATCH_THRESHOLD = 0.4


def match_name_to_player(name: str, player_directory: dict[int, dict], expected_element_type: int | None = None) -> int | None:
    """Best-guess player_id for a plain name (e.g. "Haaland", "B.Fernandes")
    against `player_directory` (id -> {web_name, element_type, ...}).

    When `expected_element_type` is given, an exact position match is
    preferred over a higher text-similarity score at a different position --
    this disambiguates two players who share a surname (e.g. two different
    "Palmer"s) using the position implied by the squad slot being filled.
    Returns None rather than a wild guess if nothing resembles `name` at all.
    """
    name_lower = name.strip().lower()
    if not name_lower:
        return None

    best_id, best_key = None, (False, 0.0)
    for player_id, info in player_directory.items():
        web_name = (info.get("web_name") or "").strip().lower()
        if not web_name:
            continue
        ratio = SequenceMatcher(None, name_lower, web_name).ratio()
        position_match = expected_element_type is not None and info.get("element_type") == expected_element_type
        key = (position_match, ratio)
        if key > best_key:
            best_id, best_key = player_id, key

    return best_id if best_key[1] >= MATCH_THRESHOLD else None
