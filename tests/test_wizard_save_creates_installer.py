"""Saving a wizard offers to build the installer (VB ``RunCreateModInstaller``).

NIT asks "Do you want to (re-)create the Mod Installer for X?" after the Wizard
Builder is saved, with "Always take this action" (``ConfigRunCreateInstaller``).
Vaultkeeper saved the wizard and left the installer as it was, so the wizard had
no effect until the user rebuilt by hand (logic audit 3f).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from vaultkeeper.config.settings import load_settings, save_settings
from vaultkeeper.ui.controller import ProfileController


def _window(qtbot, tmp_path: Path):
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Alpha")
    (profile_mods / "Alpha" / "alpha.hak").write_text("A")
    win = MainWindow(c)
    qtbot.addWidget(win)
    return win, c


def _builder(win, c):
    from vaultkeeper.ui.dialogs.wizard_builder import WizardBuilder

    return WizardBuilder(c, "Alpha", win)


def test_yes_builds_the_installer(qtbot, tmp_path: Path, monkeypatch) -> None:
    win, c = _window(qtbot, tmp_path)
    dlg = _builder(win, c)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)

    dlg._offer_create_installer()

    assert c.pd.mod_item("Alpha").is_installer()


def test_always_no_stops_asking(qtbot, tmp_path: Path, monkeypatch) -> None:
    win, c = _window(qtbot, tmp_path)
    settings = load_settings()
    settings.run_create_installer = "no"
    save_settings(settings)
    dlg = _builder(win, c)

    def fail(self):
        raise AssertionError("asked")

    monkeypatch.setattr(QMessageBox, "exec", fail)
    dlg._offer_create_installer()

    assert not c.pd.mod_item("Alpha").is_installer()


def test_install_after_create_reinstalls_an_installed_mod(qtbot, tmp_path: Path) -> None:
    """VB ``BehaviourInstallerInstall`` installs every mod built. The rebuild
    uninstalls an installed mod first, and Vaultkeeper then skipped it because it
    *had been* installed, so the preference left it uninstalled."""
    win, c = _window(qtbot, tmp_path)
    settings = load_settings()
    settings.install_after_create = True
    settings.installer_restore = False
    save_settings(settings)
    win._on_create_installer(["Alpha"])
    assert c._mod_installed("Alpha")

    win._on_create_installer(["Alpha"])

    assert c._mod_installed("Alpha")
