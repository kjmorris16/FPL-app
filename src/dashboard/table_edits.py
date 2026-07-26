"""Pure logic for turning a direct edit to the pre-season squad table's
"Player" column into extra must-include/must-exclude picks. Kept separate
from app.py (and its `st.data_editor` call, which Streamlit's `AppTest`
can't currently drive) so this part is unit-testable on its own.
"""


def apply_name_edits(
    original_squad: list[dict],
    edited_names: list[str],
    player_directory: dict[int, dict],
    include_ids: set[int],
    exclude_ids: set[int],
) -> tuple[set[int], set[int], list[str]]:
    """`original_squad` and `edited_names` must be in the same row order as
    the table the user edited. A row whose name changed to a name that
    matches exactly one other player swaps that player in and the row's
    original player out, layered on top of `include_ids`/`exclude_ids`.

    Returns `(updated_include_ids, updated_exclude_ids, unmatched_names)` --
    a typed name that doesn't match exactly one player is left unapplied
    (reported in `unmatched_names`) rather than silently doing nothing or
    guessing, so a typo doesn't quietly fail to swap anyone.
    """
    updated_include = set(include_ids)
    updated_exclude = set(exclude_ids)
    unmatched = []

    for original_player, new_name in zip(original_squad, edited_names):
        old_id = original_player["player_id"]
        old_name = player_directory.get(old_id, {}).get("web_name", "")
        new_name = (new_name or "").strip()
        if not new_name or new_name.lower() == old_name.strip().lower():
            continue

        matches = [
            pid for pid, info in player_directory.items()
            if info["web_name"].strip().lower() == new_name.lower()
        ]
        if len(matches) != 1:
            unmatched.append(new_name)
            continue

        new_id = matches[0]
        if new_id == old_id:
            continue

        updated_exclude.discard(new_id)
        updated_include.discard(old_id)
        updated_include.add(new_id)
        updated_exclude.add(old_id)

    return updated_include, updated_exclude, unmatched
