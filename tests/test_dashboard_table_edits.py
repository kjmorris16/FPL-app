from src.dashboard.table_edits import apply_label_edits

LABEL_BY_ID = {
    1: "Salah (MID, LIV) #1",
    2: "Haaland (FWD, MCI) #2",
    3: "Saka (MID, ARS) #3",
    4: "Palmer (MID, CHE) #4",
}
ID_BY_LABEL = {label: pid for pid, label in LABEL_BY_ID.items()}


def test_apply_label_edits_no_changes_returns_same_sets():
    squad = [{"player_id": 1}, {"player_id": 2}]
    labels = [LABEL_BY_ID[1], LABEL_BY_ID[2]]
    include, exclude = apply_label_edits(squad, labels, LABEL_BY_ID, ID_BY_LABEL, set(), set())
    assert include == set()
    assert exclude == set()


def test_apply_label_edits_valid_swap_updates_sets():
    squad = [{"player_id": 1}, {"player_id": 2}]
    labels = [LABEL_BY_ID[3], LABEL_BY_ID[2]]  # row 1: Salah -> Saka
    include, exclude = apply_label_edits(squad, labels, LABEL_BY_ID, ID_BY_LABEL, set(), set())
    assert include == {3}
    assert exclude == {1}


def test_apply_label_edits_preserves_existing_include_exclude_from_elsewhere():
    squad = [{"player_id": 1}]
    labels = [LABEL_BY_ID[3]]
    include, exclude = apply_label_edits(squad, labels, LABEL_BY_ID, ID_BY_LABEL, {4}, {2})
    assert include == {3, 4}
    assert exclude == {1, 2}


def test_apply_label_edits_multiple_rows_edited_at_once():
    squad = [{"player_id": 1}, {"player_id": 2}]
    labels = [LABEL_BY_ID[3], LABEL_BY_ID[4]]
    include, exclude = apply_label_edits(squad, labels, LABEL_BY_ID, ID_BY_LABEL, set(), set())
    assert include == {3, 4}
    assert exclude == {1, 2}


def test_apply_label_edits_unknown_label_is_ignored():
    squad = [{"player_id": 1}]
    labels = ["Not A Real Label"]
    include, exclude = apply_label_edits(squad, labels, LABEL_BY_ID, ID_BY_LABEL, set(), set())
    assert include == set()
    assert exclude == set()


def test_apply_label_edits_selecting_the_same_player_again_is_a_no_op():
    squad = [{"player_id": 1}]
    labels = [LABEL_BY_ID[1]]
    include, exclude = apply_label_edits(squad, labels, LABEL_BY_ID, ID_BY_LABEL, set(), set())
    assert include == set()
    assert exclude == set()


def test_apply_label_edits_editing_a_previously_swapped_in_row_further_updates_the_sets():
    # Row currently holds player 3 (a prior swap already forced it in, id 1
    # out); editing that same row again to player 4 should force 4 in and 3
    # out, on top of the existing constraints rather than replacing them.
    squad = [{"player_id": 3}]
    labels = [LABEL_BY_ID[4]]
    include, exclude = apply_label_edits(squad, labels, LABEL_BY_ID, ID_BY_LABEL, {3}, {1})
    assert include == {4}
    assert exclude == {1, 3}
