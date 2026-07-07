"""Tests for the Settings dialog."""

from __future__ import annotations

from vaultkeeper.config.settings import Settings
from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog


def test_dialog_reflects_settings(qtbot):
    settings = Settings(
        recycle_on_delete=False,
        validate_game_config_on_startup=True,
        nwn_path="/games/NWN",
        active_profile="My Mods",
    )
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert not dlg.recycle.isChecked()
    assert dlg.startup_check.isChecked()


def test_apply_to_writes_back(qtbot):
    settings = Settings(recycle_on_delete=True, validate_game_config_on_startup=True)
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg.recycle.setChecked(False)
    dlg.startup_check.setChecked(False)
    dlg.apply_to(settings)
    assert settings.recycle_on_delete is False
    assert settings.validate_game_config_on_startup is False


def test_edit_persists_on_accept(qtbot, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    from vaultkeeper.config.settings import save_settings

    save_settings(Settings(recycle_on_delete=True), settings_path)

    # Simulate the user unchecking recycle and pressing OK.
    def fake_exec(self):
        self.recycle.setChecked(False)
        return SettingsDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    result = SettingsDialog.edit(settings_path)
    assert result is not None
    assert result.recycle_on_delete is False

    from vaultkeeper.config.settings import load_settings

    assert load_settings(settings_path).recycle_on_delete is False


def test_edit_cancel_returns_none(qtbot, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(
        SettingsDialog, "exec", lambda self: SettingsDialog.DialogCode.Rejected
    )
    assert SettingsDialog.edit(settings_path) is None
