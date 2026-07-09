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
    assert len(report["folders"]) == len(default_dir_mapping())

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
