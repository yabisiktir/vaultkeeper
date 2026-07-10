"""Tests for the RunWizard install-time prompt dialog + main-window flow."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.game.wizard import WIZARD_FILE  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.wizard_prefs import WizardPreferencesDialog  # noqa: E402


def test_prefs_dialog_checked_keys(qtbot):
    prefs = [
        {"key": "a.hak", "display": "A", "checked": True},
        {"key": "b.hak", "display": "B", "checked": False},
    ]
    dlg = WizardPreferencesDialog("T", "Choose", prefs)
    qtbot.addWidget(dlg)
    assert dlg.checked_keys() == {"a.hak"}  # only the default-checked one


def _controller(tmp_path: Path, mod: str) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    (profile_mods / mod / C.MOD_INSTALLER_DIR).mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_create_installer_runs_wizard_flow(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path, "Choicey")
    mod = tmp_path / "Profiles" / "P" / "Choicey"
    (mod / "hak" / "hi.hak").parent.mkdir(parents=True)
    (mod / "hak" / "hi.hak").write_bytes(b"x")
    (mod / "hak" / "lo.hak").write_bytes(b"x")
    (mod / WIZARD_FILE).write_text(
        "SelectOne = Pick\n\thak\\hi.hak > Hi\n\thak\\lo.hak > Lo\nEnd SelectOne",
        encoding="utf-8",
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)

    # User picks "Hi" in the SelectOne dialog.
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("Hi", True))
    choice, checked = win._run_installer_wizard("Choicey")
    assert choice == "hak\\hi.hak"
    assert checked is None  # no SelectMany
