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


# -- Archive / reduce / restore (VB ArchiveGames / RestoreGames) ----------- #


def _seed_archive(controller: ProfileController) -> Path:
    """Create an archived range for the current game ("Adventure") on disk.

    Uses a folder number that does not collide with the live saves so a restore can
    move it back cleanly.
    """
    root = controller.archived_saves_root() / "Adventure" / "000005-000005"
    save = root / "000005 - archived"
    save.mkdir(parents=True)
    (save / "Adventure.sav").write_bytes(b"\x00" * 16)
    (save / "savenfo.txt").write_text("Aarin's Lodge", encoding="utf-8")
    return root


def test_report_lists_archived_ranges(qtbot, tmp_path):
    controller = _controller(tmp_path)
    _seed_archive(controller)
    report = controller.game_saves_report()
    assert report["archived"] == [
        {"range": "000005-000005", "count": 1, "size": report["archived"][0]["size"]}
    ]
    assert report["archived"][0]["count"] == 1


def test_reduce_game_saves_controller(tmp_path):
    controller = _controller(tmp_path)
    saves = controller.ctx.game_user_dir / "saves"
    # Add enough standard saves that a keep=1 reduce archives some.
    for n in (3, 4, 5):
        d = saves / f"00000{n} - std"
        d.mkdir(parents=True)
        (d / "Adventure.sav").write_bytes(b"\x00" * 16)
        (d / "savenfo.txt").write_text("Woods", encoding="utf-8")
    result = controller.reduce_game_saves(1)
    assert result["ok"] is True
    assert result["moved"] >= 1
    # The archive now exists and shows up in the report.
    assert controller.game_saves_report()["archived"]


def test_restore_archived_saves_controller(tmp_path):
    controller = _controller(tmp_path)
    _seed_archive(controller)
    result = controller.restore_archived_saves("000005-000005")
    assert result["ok"] is True
    assert result["restored"] == 1
    # The save came back and the archive folder is gone.
    assert (controller.ctx.game_user_dir / "saves" / "000005 - archived").is_dir()
    assert not controller.game_saves_report()["archived"]


def test_dialog_restore_button(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    controller = _controller(tmp_path)
    _seed_archive(controller)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    assert dlg.archives.topLevelItemCount() == 1
    assert not dlg.restore_button.isEnabled()  # nothing selected yet
    dlg.archives.setCurrentItem(dlg.archives.topLevelItem(0))
    assert dlg.restore_button.isEnabled()

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg._on_restore()
    # After restore the archives list is empty and the save is back.
    assert dlg.archives.topLevelItemCount() == 0
    assert (controller.ctx.game_user_dir / "saves" / "000005 - archived").is_dir()


def test_dialog_reduce_button_dispatch(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    calls = []
    monkeypatch.setattr(
        controller,
        "reduce_game_saves",
        lambda keep, **kw: calls.append(keep) or {"ok": True, "message": "done"},
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg.keep_spin.setValue(30)
    dlg._on_reduce()
    assert calls == [30]


# -- Deactivate / Activate / Delete (VB GameManager backup flows) ---------- #


def test_deactivate_and_report(qtbot, tmp_path):
    controller = _controller(tmp_path)
    result = controller.deactivate_current_game()
    assert result["ok"]
    assert result["moved"] == 2
    # Live saves are gone; the deactivated game shows up in the backup report.
    assert controller.game_saves_report()["count"] == 0
    dg = controller.deactivated_games_report()
    assert dg["games"][0]["name"] == "Adventure"
    assert dg["games"][0]["count"] == 2
    assert dg["backup_total_bytes"] > 0


def test_activate_restores_deactivated_game(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.deactivate_current_game()
    assert controller.game_saves_report()["count"] == 0

    result = controller.activate_game("Adventure")
    assert result["ok"]
    assert controller.game_saves_report()["count"] == 2
    # The backup folder is gone after activation.
    assert controller.deactivated_games_report()["games"] == []


def test_delete_game_backup(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.deactivate_current_game()
    result = controller.delete_game_backup("Adventure")
    assert result["ok"]
    assert controller.deactivated_games_report()["games"] == []


def test_dialog_deactivate_button(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    assert dlg.deactivate_button.isEnabled()
    dlg._on_deactivate()
    # The second list now shows the deactivated game.
    assert dlg.games.topLevelItemCount() == 1
    assert dlg.games.topLevelItem(0).text(0) == "Adventure"
    # Active list emptied.
    assert dlg.table.topLevelItemCount() == 0


def test_opening_the_manager_moves_other_mods_saves_aside(qtbot, tmp_path):
    """VB does this from PopulateSaveList, so it happens on the way in — and the
    report has to be taken afterwards or it describes a folder that has moved."""
    controller = _controller(tmp_path)
    other = tmp_path / "gameuser" / "saves" / "000005 - other"
    other.mkdir(parents=True)
    (other / "Chapter Two.sav").write_bytes(b"\x00" * 32)
    (other / "savenfo.txt").write_text("Elsewhere", encoding="utf-8")

    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    assert "Auto-Backup" in dlg.status.text()

    # The invariant, not a particular folder: the live folder holds saves for
    # one mod only (the newest is the one being played), and the quicksave stays
    # wherever it is. Asserting which mod wins would just re-implement
    # current_game_save in the test.
    report = controller.game_saves_report()
    standard = {
        r["save"] for r in report["rows"] if not r["name"].startswith(("000000", "000001"))
    }
    assert len(standard) == 1, standard
    assert any(r["name"] == "000000 - quicksave" for r in report["rows"])

    backups = controller.game_backup_root()
    moved = [p.name for p in backups.iterdir()] if backups.is_dir() else []
    assert len(moved) == 1 and moved[0] not in standard


def test_opening_the_manager_says_nothing_when_there_is_one_mod(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.status.text() == ""
