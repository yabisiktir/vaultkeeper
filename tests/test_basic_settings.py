"""Tests for the curated Basic Settings dialog (VB BasicSettings)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.ui.dialogs.basic_settings import BasicSettingsDialog


def test_dialog_has_two_curated_tabs(qtbot) -> None:
    dlg = BasicSettingsDialog(Settings())
    qtbot.addWidget(dlg)
    # Distinct from the full Settings browser: exactly Behaviour + User Interface.
    assert [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())] == [
        "Behaviour",
        "User Interface",
    ]


def test_dialog_reflects_and_applies_settings(qtbot) -> None:
    s = Settings()
    s.install_after_create = True
    s.select_game_mod = True
    s.splitter_width = 3
    s.copy_debug_mode_on_play = "DebugMode 1"
    dlg = BasicSettingsDialog(s)
    qtbot.addWidget(dlg)
    assert dlg.cb_install_auto.isChecked()
    assert dlg.cb_select_game_mod.isChecked()
    assert dlg.cb_copy_debug.isChecked()
    assert dlg._selected_splitter_width() == 3

    # Toggle a couple and apply back.
    dlg.cb_auto_character.setChecked(True)
    dlg.cb_copy_debug.setChecked(False)
    out = Settings()
    dlg.apply_to(out)
    assert out.auto_character is True
    assert out.copy_debug_mode_on_play == ""  # unchecked -> empty
    assert out.install_after_create is True
    assert out.splitter_width == 3


def test_install_auto_forces_restore_coupling(qtbot) -> None:
    dlg = BasicSettingsDialog(Settings())
    qtbot.addWidget(dlg)
    assert not dlg.cb_install_restore.isChecked()
    dlg.cb_install_auto.setChecked(True)  # VB: forces "already installed" on
    assert dlg.cb_install_restore.isChecked()


def test_advanced_button_signals_chain(qtbot) -> None:
    dlg = BasicSettingsDialog(Settings())
    qtbot.addWidget(dlg)
    assert dlg.advanced_requested is False
    dlg._on_advanced()
    assert dlg.advanced_requested is True


def test_edit_round_trips_new_fields(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_settings(Settings(), path)

    # Simulate the dialog changing fields then persisting.
    s = load_settings(path)
    dlg = BasicSettingsDialog(s)
    qtbot.addWidget(dlg)
    dlg.cb_select_game_mod.setChecked(True)
    dlg.cb_copy_mod_name.setChecked(True)
    for rb in dlg._splitter_radios:
        if rb.property("splitter_width") == 4:
            rb.setChecked(True)
    dlg.apply_to(s)
    save_settings(s, path)

    reloaded = load_settings(path)
    assert reloaded.select_game_mod is True
    assert reloaded.copy_mod_name_on_play is True
    assert reloaded.splitter_width == 4
