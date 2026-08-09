"""Customise the Quick Access Toolbar (VB MsCustomise + MsShowText).

mstoolbareditorhelp.htm and newtopic35.htm. Both were recorded as gaps: the
toolbar was fixed, and the two Options items that govern it did nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.config.settings import load_settings, save_settings
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.toolbar_editor import ToolbarEditor
from vaultkeeper.ui.main_window import MainWindow
from vaultkeeper.ui.quick_toolbar import (
    QUICK_ITEMS,
    SEP,
    ToolItem,
    items_from_settings,
    items_to_settings,
)


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    settings = load_settings()
    settings.quick_toolbar_items = []
    settings.toolbar_show_text = True
    save_settings(settings)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


# -- The saved form -------------------------------------------------------------- #
def test_nothing_saved_means_the_default_strip():
    assert items_from_settings([]) == QUICK_ITEMS


def test_a_saved_list_round_trips():
    items = (ToolItem("TsFind", "Search16", "Find"), SEP, ToolItem("TsCut", "Cut-006", "Snip"))
    assert items_from_settings(items_to_settings(items)) == items


def test_an_entry_missing_its_icon_borrows_the_default_one():
    """The editor never lets anyone choose an icon, so one is never stored by
    hand — but a hand-edited settings file should still produce a button."""
    restored = items_from_settings([{"action": "TsFind", "caption": "Find"}])
    assert restored[0].image == "Search16"


# -- The editor ------------------------------------------------------------------ #
def _editor(qtbot, items=None, available=None) -> ToolbarEditor:
    dlg = ToolbarEditor(
        items if items is not None else QUICK_ITEMS,
        available if available is not None else [ToolItem("MsFind", "Search16", "Find")],
    )
    qtbot.addWidget(dlg)
    return dlg


def test_adding_puts_the_command_after_the_selected_row(qtbot):
    dlg = _editor(qtbot, items=(ToolItem("TsCut", "Cut-006", "Cut"),))
    dlg.current.setCurrentRow(0)
    dlg.available.setCurrentRow(0)
    dlg._on_add()

    assert [i.action for i in dlg.items()] == ["TsCut", "MsFind"]


def test_removing_and_reordering(qtbot):
    dlg = _editor(
        qtbot,
        items=(
            ToolItem("TsCut", "Cut-006", "Cut"),
            ToolItem("TsCopy", "CopyOffice2016", "Copy"),
        ),
    )
    dlg.current.setCurrentRow(1)
    dlg._move(-1)
    assert [i.action for i in dlg.items()] == ["TsCopy", "TsCut"]

    dlg._on_remove()
    assert [i.action for i in dlg.items()] == ["TsCut"]


def test_the_caption_can_be_shortened(qtbot):
    """"You can shorten the text that will be displayed under the icon"."""
    dlg = _editor(qtbot, items=(ToolItem("TsCreateInstaller", "FolderMapping16", "Installer"),))
    dlg.current.setCurrentRow(0)
    assert dlg.caption.text() == "Installer"

    dlg._on_caption_edited("Build")
    assert dlg.items()[0].caption == "Build"
    assert dlg.items()[0].action == "TsCreateInstaller", "still the same command"


def test_a_separator_has_no_caption_to_edit(qtbot):
    dlg = _editor(qtbot, items=(SEP,))
    dlg.current.setCurrentRow(0)
    assert not dlg.caption.isEnabled()


def test_restore_defaults_puts_the_original_strip_back(qtbot):
    dlg = _editor(qtbot, items=(ToolItem("TsCut", "Cut-006", "Cut"),))
    dlg._on_restore()
    assert dlg.items() == QUICK_ITEMS


# -- In the window --------------------------------------------------------------- #
def test_only_working_commands_with_an_icon_are_offered(qtbot, controller):
    """The toolbar shows icons and may show *only* icons, so a command with no
    image is a blank square and a greyed one is a button that does nothing."""
    win = MainWindow(controller)
    qtbot.addWidget(win)

    candidates = win._toolbar_candidates()
    implemented = win.implemented_commands()
    assert candidates, "something should be offerable"
    assert all(c.image for c in candidates)
    assert all(c.action in implemented for c in candidates)
    assert all("&" not in c.caption for c in candidates)


def test_show_text_toggles_the_captions_and_persists(qtbot, controller):
    from PySide6.QtCore import Qt

    win = MainWindow(controller)
    qtbot.addWidget(win)

    win.nit_menu.action("MsShowText").setChecked(False)
    assert win.quick_toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert load_settings().toolbar_show_text is False

    win.nit_menu.action("MsShowText").setChecked(True)
    assert (
        win.quick_toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextUnderIcon
    )


def test_opening_the_window_does_not_write_settings(qtbot, controller, monkeypatch):
    """Setting the initial tick *is* the command, so it would otherwise save the
    settings file on every launch."""
    import vaultkeeper.config.settings as S

    saved: list[int] = []
    monkeypatch.setattr(S, "save_settings", lambda *a, **k: saved.append(1))
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert saved == []


def test_a_saved_toolbar_is_used_at_startup(qtbot, controller):
    settings = load_settings()
    settings.quick_toolbar_items = items_to_settings(
        (ToolItem("TsFind", "Search16", "Look"),)
    )
    save_settings(settings)

    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert list(win.quick_toolbar.actions_by_id) == ["TsFind"]
    assert win.quick_toolbar.actions_by_id["TsFind"].text() == "Look"


def test_a_rebuilt_toolbar_still_runs_its_commands(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # No reconnect needed: the signal belongs to the toolbar, not the buttons.
    win.quick_toolbar.populate((ToolItem("TsFind", "Search16", "Find"),))

    fired: list[str] = []
    win._on_find = lambda: fired.append("find")
    win.quick_toolbar.actions_by_id["TsFind"].trigger()
    assert fired == ["find"]
