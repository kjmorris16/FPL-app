from src.dashboard import manual_squad
from src.scoring.constants import DEF, FWD, GK, MID

DIRECTORY = {
    1: {"web_name": "Haaland", "element_type": FWD},
    2: {"web_name": "Salah", "element_type": MID},
    3: {"web_name": "Palmer", "element_type": MID},  # Cole Palmer, a midfielder
    4: {"web_name": "Palmer", "element_type": GK},  # a same-surname goalkeeper
    5: {"web_name": "Fernandes", "element_type": MID},
}


def test_match_name_to_player_exact_match():
    assert manual_squad.match_name_to_player("Haaland", DIRECTORY) == 1


def test_match_name_to_player_close_match_still_resolves():
    assert manual_squad.match_name_to_player("Halaand", DIRECTORY) == 1


def test_match_name_to_player_no_resemblance_returns_none():
    assert manual_squad.match_name_to_player("Zzznotarealplayer", DIRECTORY) is None


def test_match_name_to_player_empty_name_returns_none():
    assert manual_squad.match_name_to_player("", DIRECTORY) is None


def test_match_name_to_player_disambiguates_shared_surname_by_expected_position():
    # "Palmer" alone is ambiguous between a MID and a GK -- the expected
    # position (known from which squad slot is being filled) should win.
    assert manual_squad.match_name_to_player("Palmer", DIRECTORY, expected_element_type=GK) == 4
    assert manual_squad.match_name_to_player("Palmer", DIRECTORY, expected_element_type=MID) == 3


def test_match_name_to_player_without_expected_position_still_returns_a_match():
    assert manual_squad.match_name_to_player("Palmer", DIRECTORY) in (3, 4)


def test_suggested_squad_hints_has_fifteen_players_with_exactly_one_captain_and_one_vice():
    hints = manual_squad.SUGGESTED_SQUAD_HINTS
    assert len(hints) == 15
    roles = [role for _name, _pos, role in hints]
    assert roles.count("C") == 1
    assert roles.count("VC") == 1


def test_suggested_squad_hints_positions_are_valid():
    valid_positions = {GK, DEF, MID, FWD}
    assert all(pos in valid_positions for _name, pos, _role in manual_squad.SUGGESTED_SQUAD_HINTS)
