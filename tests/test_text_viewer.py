"""Tests for the TextViewer dialog and the file-path helpers."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.text_viewer import TextViewer


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.ctx.game_user_dir = tmp_path / "gameuser"
    return controller


def test_viewer_loads_file(qtbot, tmp_path):
    log = tmp_path / "nit.log"
    log.write_text("line one\nline two\n", encoding="utf-8")
    dlg = TextViewer.show_file(log, "NIT Log File")
    qtbot.addWidget(dlg)
    assert "line one" in dlg.editor.toPlainText()


def test_viewer_missing_file(qtbot, tmp_path):
    dlg = TextViewer.show_file(tmp_path / "nope.txt", "Missing")
    qtbot.addWidget(dlg)
    assert "not found" in dlg.editor.toPlainText()


def test_viewer_none_path(qtbot):
    dlg = TextViewer.show_file(None, "None")
    qtbot.addWidget(dlg)
    assert "no file available" in dlg.editor.toPlainText()


def test_controller_file_paths(qtbot, tmp_path):
    controller = _controller(tmp_path)
    assert controller.game_file_path("logs", "nwclientlog1.txt") == (
        tmp_path / "gameuser" / "logs" / "nwclientlog1.txt"
    )
    assert controller.nit_log_path().name  # the app log has a name


def test_game_file_path_none_without_user_dir(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.ctx.game_user_dir = None
    assert controller.game_file_path("nwn.ini") is None
