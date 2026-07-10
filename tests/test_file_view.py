"""Tests for the FileView pane widget."""

from __future__ import annotations

from PySide6.QtCore import Qt

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.ui.file_view import FileView


def _mod(name: str, state: State = State.NOT_INSTALLED) -> ModData:
    return ModData(group="Adventures", mod_name=name, mod_state=state)


def test_populate_groups_and_mods(qtbot):
    fv = FileView()
    qtbot.addWidget(fv)
    fv.populate([("Adventures", [_mod("Alpha"), _mod("Beta")])])
    assert fv.topLevelItemCount() == 1
    group = fv.topLevelItem(0)
    assert group.text(0) == "Adventures"
    assert group.childCount() == 2
    # Group rows are not selectable; mod rows are.
    assert not (group.flags() & Qt.ItemFlag.ItemIsSelectable)


def test_hidden_group_shows_mods_at_top_level(qtbot):
    from vaultkeeper.core import constants as C

    fv = FileView()
    qtbot.addWidget(fv)
    # The "No Group" bucket ("......001") has no header row; its mods are top-level.
    fv.populate([(C.GROUP_NONE, [_mod("Loose 1"), _mod("Loose 2")])])
    assert fv.topLevelItemCount() == 2
    labels = {fv.topLevelItem(i).text(0) for i in range(2)}
    assert labels == {"Loose 1", "Loose 2"}
    # No raw "......001" sentinel is shown anywhere.
    assert all(not fv.topLevelItem(i).text(0).startswith("......") for i in range(2))
    # A top-level mod row is still selectable.
    assert fv.topLevelItem(0).flags() & Qt.ItemFlag.ItemIsSelectable


def test_mixed_hidden_and_named_groups(qtbot):
    from vaultkeeper.core import constants as C

    fv = FileView()
    qtbot.addWidget(fv)
    fv.populate(
        [(C.GROUP_NONE, [_mod("Loose")]), ("Adventures", [_mod("Alpha")])]
    )
    # One top-level mod (ungrouped) + one group header (Adventures).
    assert fv.topLevelItemCount() == 2
    top_texts = [fv.topLevelItem(i).text(0) for i in range(2)]
    assert "Loose" in top_texts
    assert "Adventures" in top_texts


def test_installed_mod_marked_and_coloured(qtbot):
    fv = FileView()
    qtbot.addWidget(fv)
    fv.populate([("Adventures", [_mod("Alpha", State.INSTALLED)])])
    child = fv.topLevelItem(0).child(0)
    assert "✓" in child.text(0)
    assert child.foreground(0).color().green() > 100  # green-ish
    assert not child.icon(0).isNull()


def test_state_icon_names_resolve(qtbot):
    from vaultkeeper.ui import resources as R

    for state in (
        State.INSTALLED,
        State.MATCH_OVERRIDE,
        State.OVERRIDDEN,
        State.NOT_INSTALLED,
        State.NONE,
    ):
        name = FileView.state_icon_name(_mod("X", state))
        assert R.icon_exists(name), f"missing state icon {name} for {state}"


def test_selection_reports_mod_names(qtbot):
    fv = FileView()
    qtbot.addWidget(fv)
    fv.populate([("Adventures", [_mod("Alpha"), _mod("Beta")])])
    child = fv.topLevelItem(0).child(1)
    seen: list[list[str]] = []
    fv.selection_changed.connect(seen.append)
    child.setSelected(True)
    assert fv.selected_mod_names() == ["Beta"]
    assert seen and seen[-1] == ["Beta"]
