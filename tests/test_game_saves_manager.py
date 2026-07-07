"""Tests for the game-saves report + manager dialog."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.game_saves_manager import GameSavesManager


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    f = profile_mods / "Alpha" / C.MOD_INSTALLER_DIR / "hak" / "x.hak"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    # Redirect the play loop at an isolated game-user dir with saves.
    controller.ctx.game_user_dir = tmp_path / "gameuser"
    saves = tmp_path / "gameuser" / "saves"
    for folder, sav, loc in [
        ("000000 - quicksave", "Adventure", "Aarin's Lodge"),
        ("000002 - camp", "Adventure", "The Wood"),
    ]:
        d = saves / folder
        d.mkdir(parents=True)
        (d / f"{sav}.sav").write_bytes(b"\x00" * 32)
        (d / "savenfo.txt").write_text(loc, encoding="utf-8")
    return controller


def test_game_saves_report_lists_saves(qtbot, tmp_path):
    controller = _controller(tmp_path)
    report = controller.game_saves_report()
    assert report["count"] == 2
    assert report["current"] == "Adventure"
    names = [r["name"] for r in report["rows"]]
    assert "000000 - quicksave" in names
    # A row carries the location read from savenfo.txt.
    locs = [r["location"] for r in report["rows"]]
    assert "Aarin's Lodge" in locs


def test_manager_dialog_populates(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 2
    assert dlg.table.topLevelItem(0).text(1) == "Adventure"


def test_report_empty_without_saves(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.ctx.game_user_dir = tmp_path / "empty"  # no saves dir
    controller._play_loop = None  # rebuild the loop against the new dir
    report = controller.game_saves_report()
    assert report["count"] == 0
    assert report["rows"] == []
