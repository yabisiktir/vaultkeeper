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


# -- Web Menu editor -------------------------------------------------------- #


def test_web_menu_reflects_and_edits(qtbot):
    settings = Settings(web_links=[{"text": "Vault", "url": "https://v.example"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg.web_tree.topLevelItemCount() == 1
    assert dlg.web_tree.topLevelItem(0).text(0) == "Vault"

    # Add a link and write back.
    dlg._add_web_row("Nexus", "https://n.example")
    dlg.apply_to(settings)
    assert settings.web_links == [
        {"text": "Vault", "url": "https://v.example"},
        {"text": "Nexus", "url": "https://n.example"},
    ]


def test_web_menu_remove_and_move(qtbot):
    settings = Settings(
        web_links=[
            {"text": "A", "url": "a"},
            {"text": "B", "url": "b"},
            {"text": "C", "url": "c"},
        ]
    )
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)

    # Move B up (select index 1, move -1).
    dlg.web_tree.setCurrentItem(dlg.web_tree.topLevelItem(1))
    dlg._web_move(-1)
    assert [dlg.web_tree.topLevelItem(i).text(0) for i in range(3)] == ["B", "A", "C"]

    # Remove the currently selected (B).
    dlg._web_remove()
    assert [dlg.web_tree.topLevelItem(i).text(0) for i in range(2)] == ["A", "C"]


def test_web_menu_reset_to_defaults(qtbot):
    from vaultkeeper.config.settings import default_web_links

    settings = Settings(web_links=[{"text": "Custom", "url": "x"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg._web_reset()
    dlg.apply_to(settings)
    assert settings.web_links == default_web_links()


def test_web_menu_drops_blank_rows(qtbot):
    settings = Settings(web_links=[])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg._add_web_row("", "")  # fully blank → dropped
    dlg._add_web_row("Real", "https://r")
    assert dlg.web_links() == [{"text": "Real", "url": "https://r"}]
