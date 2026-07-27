import io

from PIL import Image, ImageDraw

from src.preseason import squad_ocr

DIRECTORY = {
    1: {"web_name": "Salah"},
    2: {"web_name": "Haaland"},
    3: {"web_name": "Saka"},
    4: {"web_name": "VanDijk"},
}


def test_match_players_from_text_matches_close_ocr_noise():
    # Typical OCR noise: a misread letter or two, plus trailing price/points
    # text on the same line -- still expected to resolve to the right player.
    text = "Saloh 5.5m 12pts\nHaaiand 14.0m 20pts\nSaka 6.5m 15pts\n"
    matches = squad_ocr.match_players_from_text(text, DIRECTORY)
    matched_ids = {pid for pid, _ratio in matches}
    assert matched_ids == {1, 2, 3}


def test_match_players_from_text_ignores_blank_lines():
    text = "Salah 5.5m\n\n\nSaka 6.5m\n"
    matches = squad_ocr.match_players_from_text(text, DIRECTORY)
    assert {pid for pid, _ratio in matches} == {1, 3}


def test_match_players_from_text_ignores_unrelated_text():
    text = "Total points: 1234\nBank: £0.5m\nGameweek 1\n"
    matches = squad_ocr.match_players_from_text(text, DIRECTORY)
    assert matches == []


def test_match_players_from_text_deduplicates_by_player_keeping_best_ratio():
    # Same player appears twice (e.g. once in a summary line, once in the
    # squad list) -- only the single best-matching line should count.
    text = "Salah\nSalah 5.5m 12pts\n"
    matches = squad_ocr.match_players_from_text(text, DIRECTORY)
    matched_ids = [pid for pid, _ratio in matches]
    assert matched_ids.count(1) == 1


def test_match_players_from_text_returns_empty_for_empty_text():
    assert squad_ocr.match_players_from_text("", DIRECTORY) == []


def test_match_players_from_text_returns_sorted_by_descending_confidence():
    text = "Salah 5.5m 12pts\nSaka 6.5m 15pts\n"
    matches = squad_ocr.match_players_from_text(text, DIRECTORY)
    ratios = [ratio for _pid, ratio in matches]
    assert ratios == sorted(ratios, reverse=True)


def test_extract_text_runs_ocr_without_crashing_on_a_real_image():
    image = Image.new("RGB", (200, 60), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((5, 5), "Salah", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    text = squad_ocr.extract_text(buffer.getvalue())
    assert isinstance(text, str)
