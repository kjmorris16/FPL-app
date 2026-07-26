"""Pure logic for turning a dropdown edit to the pre-season squad table's
"Player" column into extra must-include/must-exclude picks. Kept separate
from app.py (and its `st.data_editor` call, which Streamlit's `AppTest`
can't currently drive) so this part is unit-testable on its own.
"""


def apply_label_edits(
    original_squad: list[dict],
    edited_labels: list[str],
    label_by_id: dict[int, str],
    id_by_label: dict[str, int],
    include_ids: set[int],
    exclude_ids: set[int],
) -> tuple[set[int], set[int]]:
    """`original_squad` and `edited_labels` must be in the same row order as
    the table the user edited. Each row's "Player" cell is a dropdown
    restricted to `id_by_label`'s own keys (the same options list used for
    "must include"/"must exclude" style pickers elsewhere), so every edited
    label is guaranteed to resolve to a real player -- a row whose label
    changed swaps that player in and the row's original player out, layered
    on top of `include_ids`/`exclude_ids`.

    Returns the updated `(include_ids, exclude_ids)`.
    """
    updated_include = set(include_ids)
    updated_exclude = set(exclude_ids)

    for original_player, edited_label in zip(original_squad, edited_labels):
        old_id = original_player["player_id"]
        if edited_label == label_by_id.get(old_id):
            continue

        new_id = id_by_label.get(edited_label)
        if new_id is None or new_id == old_id:
            continue

        updated_exclude.discard(new_id)
        updated_include.discard(old_id)
        updated_include.add(new_id)
        updated_exclude.add(old_id)

    return updated_include, updated_exclude
