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


def test_delete_archived_saves_goes_to_the_recycle_bin(tmp_path, recycle_bin):
    """deletearchives.htm + restoringdeletedsavesfromtherecy.htm.

    Reduce used to be a one-way door: an archived range could only be brought
    back, never thrown away.
    """
    controller = _controller(tmp_path)
    _seed_archive(controller)

    result = controller.delete_archived_saves("000005-000005")

    assert result["ok"] is True
    assert result["deleted"] == 1
    assert "recycle bin" in result["message"]
    assert not controller.game_saves_report()["archived"]
    # The promise the topic makes: it is still there to be restored.
    assert (recycle_bin / "000005-000005" / "000005 - archived").is_dir()


def test_delete_archived_saves_honours_the_preference(tmp_path, recycle_bin):
    from vaultkeeper.config.settings import load_settings, save_settings

    controller = _controller(tmp_path)
    _seed_archive(controller)
    settings = load_settings()
    settings.recycle_game_saves = False
    save_settings(settings)

    result = controller.delete_archived_saves("000005-000005")

    assert result["ok"] is True
    assert "permanently" in result["message"]
    assert list(recycle_bin.iterdir()) == []


def test_delete_archived_saves_reports_a_missing_range(tmp_path):
    controller = _controller(tmp_path)
    result = controller.delete_archived_saves("999999-999999")
    assert result["ok"] is False
    assert "not found" in result["message"]


def test_delete_game_backup_honours_the_recycle_preference(tmp_path, recycle_bin):
    """A deactivated game is a whole playthrough, and went permanently."""
    controller = _controller(tmp_path)
    controller.deactivate_current_game()

    assert controller.delete_game_backup("Adventure")["ok"]
    assert (recycle_bin / "Adventure").is_dir()

    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.recycle_game_saves = False
    save_settings(settings)
    backup = controller.game_backup_root() / "Second"
    (backup / "000001 - save").mkdir(parents=True)
    assert controller.delete_game_backup("Second")["ok"]
    # Nothing new arrived in the bin: the preference was honoured both ways.
    assert [p.name for p in recycle_bin.iterdir()] == ["Adventure"]


def test_dialog_delete_archive_button(qtbot, tmp_path, monkeypatch, recycle_bin):
    from PySide6.QtWidgets import QMessageBox

    controller = _controller(tmp_path)
    _seed_archive(controller)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    asked: list[str] = []

    def question(_parent, _title, text, *a, **k):
        asked.append(text)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    assert not dlg.delete_archive_button.isEnabled()  # nothing selected
    dlg.archives.setCurrentItem(dlg.archives.topLevelItem(0))
    assert dlg.delete_archive_button.isEnabled()
    dlg.delete_archive_button.click()

    # The prompt says whether this can be undone, because that is the setting.
    assert "restored from the recycle bin" in asked[0]
    assert (recycle_bin / "000005-000005").is_dir()
    assert dlg.archives.topLevelItemCount() == 0


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


# -- Right-click Activate: bring the mod with it (switchinggamesaves.htm) -------- #
def test_activating_with_mods_installs_the_games_mod(qtbot, tmp_path):
    """A game save is no use without the mod that wrote it, and switching
    between two campaigns otherwise means doing the install by hand."""
    from vaultkeeper.core.mod_data import ModData

    controller = _controller(tmp_path)
    controller.pd.add_mod(ModData(group="Adv", mod_name="Adventure"))
    controller.pd.add_mod(ModData(group="Adv", mod_name="Other Campaign"))

    installed: list[str] = []
    uninstalled: list[str] = []
    controller.install = lambda names: installed.extend(names) or "installed"
    controller.uninstall = lambda names: uninstalled.extend(names) or "uninstalled"
    mapper = controller.play_loop.game_mapper
    mapper.save_name_to_mod_name = lambda save, interactive=True: "Adventure"
    mapper.is_mod_name = lambda name: name in {"Adventure", "Other Campaign"}

    result = controller.swap_game_mods("Adventure")

    assert installed == ["Adventure"], result["message"]
    assert uninstalled == [], "nothing else was installed to remove"


def test_it_leaves_shared_packs_alone(qtbot, tmp_path):
    """Uninstalling everything would take CEP out from under every other mod."""
    from vaultkeeper.core.mod_data import ModData
    from vaultkeeper.core.state import State

    controller = _controller(tmp_path)
    for name in ("Adventure", "Other Campaign", "CEP 2.6"):
        controller.pd.add_mod(ModData(group="Adv", mod_name=name))
        controller.pd.mod_item(name).mod_state = State.INSTALLED

    uninstalled: list[str] = []
    controller.install = lambda names: "installed"
    controller.uninstall = lambda names: uninstalled.extend(names) or "uninstalled"
    mapper = controller.play_loop.game_mapper
    mapper.save_name_to_mod_name = lambda save, interactive=True: "Adventure"
    # CEP is not a game anyone's saves belong to, so the mapper does not know it.
    mapper.is_mod_name = lambda name: name in {"Adventure", "Other Campaign"}

    controller.swap_game_mods("Adventure")

    assert uninstalled == ["Other Campaign"]
    assert "CEP 2.6" not in uninstalled


def test_a_save_whose_mod_is_not_here_is_reported(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.play_loop.game_mapper.save_name_to_mod_name = (
        lambda save, interactive=True: "Something Else"
    )
    result = controller.swap_game_mods("Something Else")
    assert not result["ok"] and "Something Else" in result["message"]


def test_the_activate_button_offers_it_on_right_click(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    assert (
        dlg.activate_button.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
    )
    assert "Right-click" in dlg.activate_button.toolTip()


def test_deactivating_with_mods_uninstalls_the_games_mod(qtbot, tmp_path):
    """startanewgame.htm — the mirror of Activate's right-click."""
    from vaultkeeper.core.mod_data import ModData
    from vaultkeeper.core.state import State

    controller = _controller(tmp_path)
    controller.pd.add_mod(ModData(group="Adv", mod_name="Adventure"))
    controller.pd.mod_item("Adventure").mod_state = State.INSTALLED

    removed: list[str] = []
    controller.uninstall = lambda names: removed.extend(names) or "uninstalled"
    controller.play_loop.game_mapper.save_name_to_mod_name = (
        lambda save, interactive=True: "Adventure"
    )

    result = controller.uninstall_game_mod("Adventure")
    assert result["ok"] and removed == ["Adventure"]


def test_a_mod_that_is_not_installed_is_not_uninstalled(qtbot, tmp_path):
    from vaultkeeper.core.mod_data import ModData

    controller = _controller(tmp_path)
    controller.pd.add_mod(ModData(group="Adv", mod_name="Adventure"))
    touched: list[str] = []
    controller.uninstall = lambda names: touched.extend(names)
    controller.play_loop.game_mapper.save_name_to_mod_name = (
        lambda save, interactive=True: "Adventure"
    )

    result = controller.uninstall_game_mod("Adventure")
    assert result["ok"] and touched == []
    assert "was not installed" in result["message"]


def test_the_current_game_is_read_before_the_saves_move(qtbot, tmp_path):
    """Once they have moved there is nothing left to say which mod they were
    for, so the name has to be taken first."""
    controller = _controller(tmp_path)
    assert controller.current_game_name() == "Adventure"

    controller.deactivate_current_game()
    assert controller.current_game_name() != "Adventure"


def test_the_deactivate_button_offers_it_on_right_click(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    assert (
        dlg.deactivate_button.contextMenuPolicy()
        == Qt.ContextMenuPolicy.CustomContextMenu
    )
    assert "Right-click" in dlg.deactivate_button.toolTip()


# -- Finished (deletinggamesaves.htm) ------------------------------------------- #
def test_finished_archives_every_save_for_that_game(qtbot, tmp_path):
    """Finished clears a mod's saves from the active list — which is what records
    its completion — by **archiving** them, never deleting: a mis-click can't
    destroy a whole game's saves, and they stay restorable from the manager."""
    controller = _controller(tmp_path)

    saves = tmp_path / "gameuser" / "saves"
    other = saves / "000009 - elsewhere"
    other.mkdir(parents=True)
    (other / "Another Game.sav").write_bytes(b"\x00" * 32)

    result = controller.finish_game("Adventure")

    assert result["ok"] and result["removed"] == 2
    assert "archived" in result["message"].lower()
    # Only that game's saves left the active list.
    left = sorted(p.name for p in saves.iterdir())
    assert left == ["000009 - elsewhere"], "only that game's saves went"
    # ...and they are in the archive, restorable — not gone.
    archived = controller.archived_saves_root() / "Adventure" / "000000-000002"
    assert sorted(p.name for p in archived.iterdir()) == [
        "000000 - quicksave",
        "000002 - camp",
    ]


def test_finished_never_deletes_even_with_the_recycle_preference_off(qtbot, tmp_path):
    """The Recycle-Bin-for-game-saves preference being off used to make Finished a
    permanent delete of a whole game's saves. It no longer deletes at all — the
    saves are archived regardless, so the footgun is closed."""
    from vaultkeeper.config.settings import load_settings, save_settings

    controller = _controller(tmp_path)
    settings = load_settings()
    settings.recycle_game_saves = False
    save_settings(settings)

    result = controller.finish_game("Adventure")
    assert result["ok"] and "archived" in result["message"].lower()
    assert "permanent" not in result["message"].lower()
    archived = controller.archived_saves_root() / "Adventure" / "000000-000002"
    assert archived.is_dir() and any(archived.iterdir())


def test_finishing_a_game_that_is_not_there_says_so(qtbot, tmp_path):
    controller = _controller(tmp_path)
    result = controller.finish_game("Never Played")
    assert not result["ok"] and "No live saves" in result["message"]


def test_the_button_needs_a_selected_save(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    dlg.table.setCurrentItem(None)
    dlg._sync_buttons()
    assert not dlg.finished_button.isEnabled()

    dlg.table.setCurrentItem(dlg.table.topLevelItem(0))
    assert dlg.finished_button.isEnabled()


def test_manager_has_its_own_documented_shortcuts(qtbot, tmp_path):
    """keyboardshortcuts.htm gives this dialog a shortcut table; it had none."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QShortcut

    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    keys = sorted(s.key().toString() for s in dlg.findChildren(QShortcut))
    assert keys == ["Ctrl++", "Ctrl+-", "Ctrl+A", "Ctrl+D", "Ctrl+O"]
    # The four action keys are dialog-scoped, so the main window's Ctrl+A
    # (Select All) is safe; Ctrl+O is scoped tighter still, to the save table.
    scopes = {
        s.key().toString(): s.context() for s in dlg.findChildren(QShortcut)
    }
    assert scopes["Ctrl+A"] == Qt.ShortcutContext.WindowShortcut
    assert scopes["Ctrl+O"] == Qt.ShortcutContext.WidgetShortcut


def test_a_shortcut_whose_button_is_disabled_does_nothing(qtbot, tmp_path, monkeypatch):
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import QMessageBox

    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: 1 / 0)

    restore = next(
        s
        for s in dlg.findChildren(QShortcut)
        if s.key() == QKeySequence("Ctrl++")
    )
    assert not dlg.restore_button.isEnabled()  # nothing archived
    restore.activated.emit()  # would raise if it clicked through


def test_save_row_right_click_offers_open_and_summary(qtbot, tmp_path):
    """openagamesavefolderwithwindowsfi.htm + newtopic60.htm: both via right-click."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QMenu

    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    dlg.table.setCurrentItem(dlg.table.topLevelItem(0))
    # Shown with popup(), not exec(): exec() is a nested loop a test cannot exit,
    # and QMenu.exec cannot be patched away in PySide6.
    dlg._show_save_menu(QPoint(4, 4))
    menu = dlg.findChild(QMenu)
    assert menu is not None
    assert [a.text() for a in menu.actions()] == [
        "Open with File Explorer",
        "Display Character Summary",
    ]
    menu.hide()


def test_save_table_ctrl_o_opens_the_folder(qtbot, tmp_path, monkeypatch):
    """The fourth way the topic names — Ctrl+O — scoped to the table."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QDesktopServices, QShortcut

    controller = _controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)

    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True
    )

    shortcut = next(
        s
        for s in dlg.table.findChildren(QShortcut)
        if s.key().toString() == "Ctrl+O"
    )
    assert shortcut.context() == Qt.ShortcutContext.WidgetShortcut
    dlg.table.setCurrentItem(dlg.table.topLevelItem(0))
    shortcut.activated.emit()
    assert len(opened) == 1
