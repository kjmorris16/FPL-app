from src.dashboard.table_edits import apply_name_edits

DIRECTORY = {
    1: {"web_name": "Salah", "element_type": 3, "team_name": "LIV"},
    2: {"web_name": "Haaland", "element_type": 4, "team_name": "MCI"},
    3: {"web_name": "Saka", "element_type": 3, "team_name": "ARS"},
    4: {"web_name": "Palmer", "element_type": 3, "team_name": "CHE"},
    5: {"web_name": "Smith", "element_type": 2, "team_name": "AAA"},
    6: {"web_name": "Smith", "element_type": 2, "team_name": "BBB"},  # duplicate display name
}


def test_apply_name_edits_no_changes_returns_same_sets():
    squad = [{"player_id": 1}, {"player_id": 2}]
    names = ["Salah", "Haaland"]
    include, exclude, unmatched = apply_name_edits(squad, names, DIRECTORY, set(), set())
    assert include == set()
    assert exclude == set()
    assert unmatched == []


def test_apply_name_edits_valid_swap_updates_sets():
    squad = [{"player_id": 1}, {"player_id": 2}]
    names = ["Saka", "Haaland"]  # row 1: Salah -> Saka
    include, exclude, unmatched = apply_name_edits(squad, names, DIRECTORY, set(), set())
    assert include == {3}
    assert exclude == {1}
    assert unmatched == []


def test_apply_name_edits_is_case_insensitive_and_trims_whitespace():
    squad = [{"player_id": 1}]
    names = ["  saka  "]
    include, exclude, unmatched = apply_name_edits(squad, names, DIRECTORY, set(), set())
    assert include == {3}
    assert exclude == {1}


def test_apply_name_edits_unmatched_name_reported_and_not_applied():
    squad = [{"player_id": 1}]
    names = ["Not A Real Player"]
    include, exclude, unmatched = apply_name_edits(squad, names, DIRECTORY, set(), set())
    assert include == set()
    assert exclude == set()
    assert unmatched == ["Not A Real Player"]


def test_apply_name_edits_ambiguous_name_reported_and_not_applied():
    squad = [{"player_id": 1}]
    names = ["Smith"]  # matches both id 5 and id 6
    include, exclude, unmatched = apply_name_edits(squad, names, DIRECTORY, set(), set())
    assert include == set()
    assert exclude == set()
    assert unmatched == ["Smith"]


def test_apply_name_edits_preserves_existing_include_exclude_from_elsewhere():
    squad = [{"player_id": 1}]
    names = ["Saka"]
    include, exclude, unmatched = apply_name_edits(squad, names, DIRECTORY, {4}, {2})
    assert include == {3, 4}
    assert exclude == {1, 2}


def test_apply_name_edits_multiple_rows_edited_at_once():
    squad = [{"player_id": 1}, {"player_id": 2}]
    names = ["Saka", "Palmer"]
    include, exclude, unmatched = apply_name_edits(squad, names, DIRECTORY, set(), set())
    assert include == {3, 4}
    assert exclude == {1, 2}


def test_apply_name_edits_typing_a_player_already_in_that_row_is_a_no_op():
    squad = [{"player_id": 1}]
    names = ["Salah"]
    include, exclude, unmatched = apply_name_edits(squad, names, DIRECTORY, set(), set())
    assert include == set()
    assert exclude == set()
    assert unmatched == []
