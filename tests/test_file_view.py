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
