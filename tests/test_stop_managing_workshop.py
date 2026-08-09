"""Disable Steam Workshop management (newtopic22.htm).

"You are asked what you want to do with the Tool's version of each Workshop
Subscription. […] Steam Workshop Subscription information is retained so that
Identifier to Mod Name mapping preferences are available in case you enable
management again."

The viewer and the refresh were ported; the way *out* of management was not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.ui.controller import ProfileController


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    for name, wid in (("Workshop Mod A", "123"), ("Workshop Mod B", "456")):
        md = ModData(group="820.  Steam Workshop", mod_name=name)
        md.workshop_id = wid
        md.web_link = f"steam://openurl/{wid}"
        c.pd.add_mod(md)
    c.pd.add_mod(ModData(group="Adv", mod_name="Ordinary Mod"))
    return c


def test_it_knows_which_mods_came_from_the_workshop(controller):
    assert controller.managed_workshop_mods() == ["Workshop Mod A", "Workshop Mod B"]


def test_keeping_them_cuts_the_steam_link(controller):
    """A mod that still claims a workshop id would be picked up as managed again
    the next time subscriptions are detected."""
    result = controller.stop_managing_workshop(keep=True)

    assert result["kept"] == 2 and result["removed"] == 0
    for name in ("Workshop Mod A", "Workshop Mod B"):
        md = controller.pd.mod_item(name)
        assert md is not None, "kept, not deleted"
        assert md.workshop_id == ""
        assert md.web_link == "", "the link pointed at the Steam item folder"
    assert controller.managed_workshop_mods() == []


def test_deleting_them_removes_the_mods(controller):
    result = controller.stop_managing_workshop(keep=False)

    assert result["removed"] == 2 and result["kept"] == 0
    assert controller.pd.mod_item("Workshop Mod A") is None
    assert controller.pd.mod_item("Ordinary Mod") is not None, "not a workshop mod"


def test_an_unmanaged_profile_says_so(tmp_path):
    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    result = c.stop_managing_workshop(keep=True)
    assert result["ok"] and "No Workshop mods" in result["message"]


def test_the_answer_says_the_mapping_is_kept(controller):
    """It is the part that was tedious to establish, so people need telling it
    survives."""
    assert "remembers which mod" in controller.stop_managing_workshop(keep=True)["message"]


def test_the_command_is_live(qtbot, controller):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert "MsStopManagingWorkshop" in win.implemented_commands()
    assert win.nit_menu.action("MsStopManagingWorkshop").isEnabled()


def test_cancelling_changes_nothing(qtbot, controller, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller)
    qtbot.addWidget(win)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: None)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)

    win._on_stop_managing_workshop()
    assert controller.managed_workshop_mods() == ["Workshop Mod A", "Workshop Mod B"]
