"""Tests for the Folder Mapping viewer (controller report + tabbed dialog).

Covers the VB Settings map-pages slice: surface the Mapper's Extension /
exception-File / Directory-Folder tables, plus the editing surface (add/update a
user override, remove an override, reset to defaults; persisted via settings).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402

from vaultkeeper.core.mapper import (  # noqa: E402
    default_dir_mapping,
    default_exception_files,
    default_ext_mapping,
)
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.folder_mapping import TAB_INDEX, FolderMapping  # noqa: E402


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    game_root = tmp_path / "steamapps" / "common" / "Neverwinter Nights"
    game_root.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
    )


# -- Controller report ---------------------------------------------------- #


def test_report_mirrors_mapper_tables(tmp_path):
    controller = _controller(tmp_path)
    report = controller.folder_mapping_report()

    assert len(report["extensions"]) == len(default_ext_mapping())
    assert len(report["files"]) == len(default_exception_files())
    # The live table: the defaults plus, on EE, the EE library folders (ovr,
    # mod, mus, txpk — VB DefineEeFolders).
    assert len(report["folders"]) == len(controller.ctx.mapper.dir_mapping)
    assert len(report["folders"]) >= len(default_dir_mapping())

    # A known extension maps to its default folder (.hak -> hak on a base install).
    by_ext = {r["ext"]: r for r in report["extensions"]}
    assert by_ext[".hak"]["folder"] == "hak"
    assert report["summary"].startswith("Extensions:")


def test_report_extension_carries_secondary_folder(tmp_path):
    controller = _controller(tmp_path)
    from vaultkeeper.core.mapper import default_folder_moves

    moves = default_folder_moves()
    by_ext = {r["ext"]: r for r in controller.folder_mapping_report()["extensions"]}
    for ext, secondary in moves.items():
        assert by_ext[ext]["secondary"] == secondary


# -- Dialog --------------------------------------------------------------- #


def test_dialog_populates_all_tabs(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = FolderMapping.show_for(controller)
    qtbot.addWidget(dlg)

    report = controller.folder_mapping_report()
    assert dlg.extensions.topLevelItemCount() == len(report["extensions"])
    assert dlg.files.topLevelItemCount() == len(report["files"])
    assert dlg.folders.topLevelItemCount() == len(report["folders"])
    # Column captions match the VB designer.
    assert dlg.extensions.headerItem().text(2) == "Secondary Folder"
    assert dlg.files.headerItem().text(0) == "File Name"
    assert dlg.folders.headerItem().text(0) == "Source Folder"


def test_dialog_opens_on_requested_tab(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = FolderMapping.show_for(controller, "Map Folders")
    qtbot.addWidget(dlg)
    assert dlg.tabs.currentIndex() == TAB_INDEX["Map Folders"]


def test_main_window_wires_map_ribbon_ids(qtbot, tmp_path):
    controller = _controller(tmp_path)
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_command("RbnMapFiles")
    assert win._folder_mapping.tabs.currentIndex() == TAB_INDEX["Map Files"]


# -- Editing (Phase 8 map customisation) ---------------------------------- #


def test_dialog_add_override_updates_table(tmp_path, qtbot) -> None:
    controller = _controller(tmp_path)
    controller._settings_path = tmp_path / "settings.json"
    dialog = FolderMapping(controller)
    qtbot.addWidget(dialog)

    dialog.tabs.setCurrentIndex(TAB_INDEX["Map Files"])
    dialog._key_edit.setText("special.hak")
    dialog._folder_combo.setCurrentText("patch")
    dialog._on_add()

    assert controller.ctx.mapper.get_mapped_folder("special.hak") == "patch"
    # The new override row appears and is bold-flagged.
    rows = {
        dialog.files.topLevelItem(i).text(0): dialog.files.topLevelItem(i)
        for i in range(dialog.files.topLevelItemCount())
    }
    assert "special.hak" in rows
    assert rows["special.hak"].data(0, Qt.ItemDataRole.UserRole)[1] is True


def test_dialog_remove_enabled_only_for_overrides(tmp_path, qtbot) -> None:
    controller = _controller(tmp_path)
    controller._settings_path = tmp_path / "settings.json"
    controller.set_map_file_exception("mine.hak", "hak")
    dialog = FolderMapping(controller, start_tab="Map Files")
    qtbot.addWidget(dialog)

    files = dialog.files
    default_item = next(
        files.topLevelItem(i)
        for i in range(files.topLevelItemCount())
        if files.topLevelItem(i).text(0) == "dialog.tlk"
    )
    override_item = next(
        files.topLevelItem(i)
        for i in range(files.topLevelItemCount())
        if files.topLevelItem(i).text(0) == "mine.hak"
    )
    files.setCurrentItem(default_item)
    assert not dialog._remove_button.isEnabled()
    files.setCurrentItem(override_item)
    assert dialog._remove_button.isEnabled()

    dialog._on_remove()
    assert not controller.ctx.mapper.is_override("exception_files", "mine.hak")


def test_dialog_excludes_tab_add_and_remove(tmp_path, qtbot) -> None:
    controller = _controller(tmp_path)
    controller._settings_path = tmp_path / "settings.json"
    dialog = FolderMapping(controller, start_tab="Map Excludes")
    qtbot.addWidget(dialog)
    assert dialog.tabs.currentIndex() == TAB_INDEX["Map Excludes"]

    dialog._key_edit.setText("mymod_bad.hak")
    dialog._folder_combo.setCurrentText("File")
    dialog._on_add()
    assert controller.ctx.mapper.is_excluded_file("mymod_bad.hak")

    rows = {
        dialog.excludes.topLevelItem(i).text(0): dialog.excludes.topLevelItem(i)
        for i in range(dialog.excludes.topLevelItemCount())
    }
    assert "mymod_bad.hak" in rows
    item = rows["mymod_bad.hak"]
    assert item.data(0, Qt.ItemDataRole.UserRole)[1] is True  # override → removable
    dialog.excludes.setCurrentItem(item)
    assert dialog._remove_button.isEnabled()
    dialog._on_remove()
    assert not controller.ctx.mapper.is_excluded_file("mymod_bad.hak")


def test_a_deletable_default_exclude_can_be_removed_and_stays_removed(tmp_path):
    # VB SetExcludes: only the mandatory defaults are locked; the rest can go.
    from vaultkeeper.config.settings import load_settings
    from vaultkeeper.core.mapper import Mapper

    c = _stage4_controller(tmp_path)
    report = c.map_excludes_report()
    removable = {r["name"]: r["removable"] for r in report["folders"]}
    assert removable["optional override files"] is True
    assert removable["__macosx"] is False
    assert any(r["name"] == "demo" for r in report["mods"])

    assert c.remove_map_exclude("folders", "optional override files")
    assert not c.remove_map_exclude("folders", "__macosx")
    assert not c.ctx.mapper.is_excluded_folder("optional override files")

    saved = load_settings(c._settings_path).map_exclude_overrides
    reopened = Mapper(exclude_overrides=saved)
    assert not reopened.is_excluded_folder("optional override files")
    reopened.add_exclude("folders", "optional override files")  # put back
    assert reopened.is_excluded_folder("optional override files")


def _stage4_controller(tmp_path):
    from vaultkeeper.ui.controller import ProfileController

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        settings_path=tmp_path / "settings.json",
    )


# -- NIT's per-row Undo and Rename Extension (Settings map pages) ------------- #
def _row(tree, text):
    return next(
        tree.topLevelItem(i)
        for i in range(tree.topLevelItemCount())
        if tree.topLevelItem(i).text(0) == text
    )


def _rows(tree):
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


def _mapping_controller(tmp_path):
    controller = _controller(tmp_path)
    controller._settings_path = tmp_path / "settings.json"
    return controller


def test_removing_an_override_keeps_the_users_exception_prefixes(tmp_path) -> None:
    """Rebuilding the defaults after a removal used to reset every extension's
    exception prefixes to the stock ones, and the next save wrote that back."""
    controller = _mapping_controller(tmp_path)
    controller.set_extension_secondary(".tga", "override", ["my_"])
    controller.set_map_file_exception("mine.hak", "hak")
    controller.remove_map_override("exception_files", "mine.hak")
    assert controller.ctx.mapper.exception_prefixes[".tga"] == ["my_"]


def test_reset_all_resets_the_saved_prefixes_too(tmp_path) -> None:
    from vaultkeeper.config.settings import load_settings
    from vaultkeeper.core.mapper import default_exception_prefixes

    controller = _mapping_controller(tmp_path)
    controller.set_extension_secondary(".tga", "override", ["my_"])
    controller.reset_map_overrides()
    saved = load_settings(controller._settings_path).map_exception_prefixes
    assert saved.get(".tga", []) == default_exception_prefixes().get(".tga", [])


def test_a_changed_row_shows_undo_and_undo_puts_it_back(tmp_path, qtbot) -> None:
    controller = _mapping_controller(tmp_path)
    controller.set_map_file_exception("mine.hak", "hak")
    dialog = FolderMapping(controller, start_tab="Map Files")
    qtbot.addWidget(dialog)
    assert not _row(dialog.files, "mine.hak").data(0, Qt.ItemDataRole.UserRole + 1)

    dialog._key_edit.setText("mine.hak")
    dialog._folder_combo.setCurrentText("patch")
    dialog._on_add()
    item = _row(dialog.files, "mine.hak")
    assert item.data(0, Qt.ItemDataRole.UserRole + 1)  # changed: Undo icon
    assert not item.icon(0).isNull()
    dialog.files.setCurrentItem(item)
    assert dialog._undo_button.isEnabled()

    dialog._on_undo()
    assert controller.ctx.mapper.get_mapped_folder("mine.hak") == "hak"
    assert not _row(dialog.files, "mine.hak").data(0, Qt.ItemDataRole.UserRole + 1)


def test_a_removed_row_stays_listed_until_undone(tmp_path, qtbot) -> None:
    controller = _mapping_controller(tmp_path)
    controller.set_map_file_exception("mine.hak", "hak")
    dialog = FolderMapping(controller, start_tab="Map Files")
    qtbot.addWidget(dialog)
    dialog.files.setCurrentItem(_row(dialog.files, "mine.hak"))
    dialog._on_remove()
    assert not controller.ctx.mapper.is_override("exception_files", "mine.hak")

    ghost = _row(dialog.files, "mine.hak")
    assert ghost.data(0, Qt.ItemDataRole.UserRole + 2)  # removed
    assert ghost.font(0).strikeOut()
    dialog.files.setCurrentItem(ghost)
    assert not dialog._remove_button.isEnabled()
    dialog._on_undo()
    assert controller.ctx.mapper.is_override("exception_files", "mine.hak")
    assert controller.ctx.mapper.get_mapped_folder("mine.hak") == "hak"


def test_undo_on_a_new_row_takes_it_away(tmp_path, qtbot) -> None:
    controller = _mapping_controller(tmp_path)
    dialog = FolderMapping(controller, start_tab="Map Folders")
    qtbot.addWidget(dialog)
    dialog._key_edit.setText("extras")
    dialog._folder_combo.setCurrentText("override")
    dialog._on_add()
    dialog.folders.setCurrentItem(_row(dialog.folders, "extras"))
    dialog._on_undo()
    assert "extras" not in _rows(dialog.folders)
    assert not controller.ctx.mapper.is_override("dir_mapping", "extras")


def test_undo_restores_an_extension_with_its_secondary_folder(tmp_path, qtbot) -> None:
    controller = _mapping_controller(tmp_path)
    mapper = controller.ctx.mapper
    before = (mapper.ext_mapping[".tga"], mapper.get_secondary_folder(".tga"),
              list(mapper.exception_prefixes.get(".tga", [])))
    dialog = FolderMapping(controller)
    qtbot.addWidget(dialog)
    controller.set_map_extension(".tga", "hak")
    controller.set_extension_secondary(".tga", "patch", ["zz_"])
    dialog.refresh()
    dialog.extensions.setCurrentItem(_row(dialog.extensions, ".tga"))
    dialog._on_undo()
    assert (mapper.ext_mapping[".tga"], mapper.get_secondary_folder(".tga"),
            list(mapper.exception_prefixes.get(".tga", []))) == before


def test_an_excluded_item_removed_comes_back_with_undo(tmp_path, qtbot) -> None:
    controller = _mapping_controller(tmp_path)
    controller.add_map_exclude("files", "junk.txt")
    dialog = FolderMapping(controller, start_tab="Map Excludes")
    qtbot.addWidget(dialog)
    dialog.excludes.setCurrentItem(_row(dialog.excludes, "junk.txt"))
    dialog._on_remove()
    assert not controller.ctx.mapper.is_excluded_file("junk.txt")
    dialog.excludes.setCurrentItem(_row(dialog.excludes, "junk.txt"))
    dialog._on_undo()
    assert controller.ctx.mapper.is_excluded_file("junk.txt")


def test_rename_extension_moves_a_customised_mapping(tmp_path, qtbot, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    controller = _mapping_controller(tmp_path)
    controller.set_map_extension(".abc", "hak")
    controller.set_extension_secondary(".abc", "override", ["x_"])
    dialog = FolderMapping(controller)
    qtbot.addWidget(dialog)
    dialog.extensions.setCurrentItem(_row(dialog.extensions, ".abc"))
    assert dialog._can_rename()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("abd", True))
    dialog._on_rename()

    mapper = controller.ctx.mapper
    assert mapper.ext_mapping[".abd"] == "hak"
    assert mapper.get_secondary_folder(".abd") == "override"
    assert mapper.exception_prefixes[".abd"] == ["x_"]
    assert ".abc" not in mapper.ext_mapping
    assert dialog.extensions.currentItem().text(0) == ".abd"


def test_a_built_in_extension_is_not_renamed(tmp_path, qtbot) -> None:
    controller = _mapping_controller(tmp_path)
    dialog = FolderMapping(controller)
    qtbot.addWidget(dialog)
    dialog.extensions.setCurrentItem(_row(dialog.extensions, ".2da"))
    assert not dialog._can_rename()
    assert not controller.rename_map_extension(".2da", "x2da")["ok"]


def test_rename_refuses_an_extension_that_already_has_a_mapping(tmp_path) -> None:
    controller = _mapping_controller(tmp_path)
    controller.set_map_extension(".abc", "hak")
    result = controller.rename_map_extension(".abc", "tga")
    assert not result["ok"]
    assert controller.ctx.mapper.ext_mapping[".abc"] == "hak"
