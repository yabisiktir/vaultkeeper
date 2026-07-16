"""Start-Screen prefix editor (VB MsEditStartScreenPrefixes)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game import start_screen as ss
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


# -- controller ------------------------------------------------------------ #
def test_prefix_text_empty_when_absent(tmp_path):
    ctrl = _controller(tmp_path)
    assert ctrl.loadscreen_prefix_text() == ""


def test_save_and_read_prefixes_round_trip(tmp_path):
    ctrl = _controller(tmp_path)
    ctrl.save_loadscreen_prefixes("Ambient\n!Disabled\n\n  \nCampaign\n")
    # Blank lines dropped; trailing whitespace trimmed.
    assert ctrl.loadscreen_prefix_text() == "Ambient\n!Disabled\nCampaign\n"
    # The prefix parser (read_prefixes) sees the enabled/disabled state.
    prefixes = ss.read_prefixes(ctrl._profile_data_dir())
    assert prefixes == {"ambient": True, "disabled": False, "campaign": True}


def test_save_empty_clears(tmp_path):
    ctrl = _controller(tmp_path)
    ctrl.save_loadscreen_prefixes("Ambient\n")
    ctrl.save_loadscreen_prefixes("")
    assert ctrl.loadscreen_prefix_text() == ""


# -- dialog ---------------------------------------------------------------- #
def test_dialog_loads_and_saves(tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.dialogs.prefix_editor import PrefixEditor

    ctrl = _controller(tmp_path)
    ctrl.save_loadscreen_prefixes("Ambient\n")
    dlg = PrefixEditor(ctrl)
    qtbot.addWidget(dlg)
    assert dlg.editor.toPlainText() == "Ambient\n"
    dlg.editor.setPlainText("Ambient\n!Old\nNew")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg._on_save()
    assert ctrl.loadscreen_prefix_text() == "Ambient\n!Old\nNew\n"


def test_command_wired_and_enabled(tmp_path, qtbot):
    from vaultkeeper.ui.main_window import MainWindow

    ctrl = _controller(tmp_path)
    win = MainWindow(controller=ctrl)
    qtbot.addWidget(win)
    assert "MsEditStartScreenPrefixes" in win.implemented_commands()
    assert win.nit_menu.actions_by_id["MsEditStartScreenPrefixes"].isEnabled()
    win._on_command("MsEditStartScreenPrefixes")
    assert win._prefix_editor.isVisible()
