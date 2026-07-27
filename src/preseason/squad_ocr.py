"""Best-effort OCR import of a user's actual FPL squad from a screenshot,
so the Pre-Season tab can score *their* picks rather than only the
optimizer's recommendation.

This is deliberately approximate: phone screenshots of the FPL app (pitch
view especially) are noisy, so OCR misreads are expected -- every match is
surfaced with its confidence, and the dashboard shows results in an
editable dropdown table (the same one used elsewhere) specifically so a
misread is a quick fix, not a dead end.
"""
import io
from difflib import SequenceMatcher

import pytesseract
from PIL import Image

MATCH_THRESHOLD = 0.5


def extract_text(image_bytes: bytes) -> str:
    """Raw OCR text from an uploaded screenshot."""
    image = Image.open(io.BytesIO(image_bytes))
    return pytesseract.image_to_string(image)


def _line_match_ratio(name: str, line: str) -> float:
    name_lower = name.lower()
    line_lower = line.lower().strip()
    if not line_lower:
        return 0.0
    # Compare the name against a same-length-ish leading slice of the line,
    # since a screenshot line is typically "name  <price>  <points>" with
    # the name itself the only part that should ever match well.
    window = line_lower[: len(name_lower) + 3]
    return SequenceMatcher(None, name_lower, window).ratio()


def match_players_from_text(text: str, player_directory: dict[int, dict]) -> list[tuple[int, float]]:
    """Matches OCR'd lines of text against `player_directory` (id -> {web_name, ...}).

    Returns up to one (player_id, confidence) per line, best match only,
    deduplicated by player (keeping the highest-confidence line for a
    player matched more than once), ordered by descending confidence.
    """
    best_by_player: dict[int, float] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        best_id, best_ratio = None, 0.0
        for player_id, info in player_directory.items():
            ratio = _line_match_ratio(info["web_name"], line)
            if ratio > best_ratio:
                best_id, best_ratio = player_id, ratio
        if best_id is not None and best_ratio >= MATCH_THRESHOLD:
            if best_ratio > best_by_player.get(best_id, 0.0):
                best_by_player[best_id] = best_ratio

    return sorted(best_by_player.items(), key=lambda item: item[1], reverse=True)
