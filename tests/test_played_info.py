"""Tests for the right-aligned MsPlayedInfo menubar item + controller summary."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.main_window import MainWindow  # noqa: E402


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    (profile_mods / "Adventure" / C.MOD_INSTALLER_DIR).mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.ctx.game_user_dir = tmp_path / "gameuser"
    (tmp_path / "gameuser" / "saves").mkdir(parents=True)
    return controller


def test_mod_played_info_summary(tmp_path):
    controller = _controller(tmp_path)
    loop = controller.play_loop
    loop.play_data.pdi.play_times["Adventure"] = timedelta(hours=3, minutes=20)
    text = controller.mod_played_info("Adventure")
    assert "Adventure played for" in text
    # An unplayed mod yields no text.
    assert controller.mod_played_info("Unknown") == ""


def test_played_info_updates_on_selection(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.play_loop.play_data.pdi.play_times["Adventure"] = timedelta(hours=1)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._update_played_info("Adventure")
    assert "Adventure played for" in win._played_info.text()
    win._update_played_info(None)
    assert win._played_info.text() == ""
