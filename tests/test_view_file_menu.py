"""Tests for the View / Diagnose file viewers (VB ``ViewIniFile_Click`` et al).

The ribbon Diagnose-tab variants (``RbnNitLog`` etc.) share handlers with the View
menu items, and the extra game ini files (player/patch/config/toolset) resolve
under the game user directory and open in the read-only text viewer.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.main_window import MainWindow  # noqa: E402


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.ctx.game_user_dir = tmp_path / "user"
    controller.ctx.game_user_dir.mkdir()
    return controller


NEW_INI_KINDS = {
    "MsNWNPlayerIniFile": ("nwnplayer.ini", "NWN Player Ini File"),
    "MsNwnPatchIniFile": ("nwnpatch.ini", "NWN Patch Ini File"),
    "MsNwnConfigIniFile": ("nwconfig.ini", "NWN Config Ini File"),
    "MsNwnToolsetIniFile": ("nwtoolset.ini", "NWN Toolset Ini File"),
}


def test_new_ini_viewers_open_correct_file(qtbot, tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    for filename, _title in NEW_INI_KINDS.values():
        (controller.ctx.game_user_dir / filename).write_text(
            f"[content of {filename}]", encoding="utf-8"
        )
    win = MainWindow(controller)
    qtbot.addWidget(win)

    for command, (filename, title) in NEW_INI_KINDS.items():
        win._on_command(command)
        viewer = win._text_viewer
        assert viewer.windowTitle() == title
        assert f"content of {filename}" in viewer.editor.toPlainText()


def test_ribbon_variants_share_view_handlers(qtbot, tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    (controller.ctx.game_user_dir / "nwn.ini").write_text("[Display]", encoding="utf-8")
    win = MainWindow(controller)
    qtbot.addWidget(win)

    win._on_command("RbnNwnIni")
    assert win._text_viewer.windowTitle() == "NWN Ini File"
    assert "[Display]" in win._text_viewer.editor.toPlainText()

    # RbnNitLog shares the NIT-log handler.
    win._on_command("RbnNitLog")
    assert win._text_viewer.windowTitle() == "NIT Log File"
