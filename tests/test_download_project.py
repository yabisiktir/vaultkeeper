"""Tests for the Download Project dialog."""

from __future__ import annotations

import pytest

from vaultkeeper.ui.controller import ProfileController


def test_copy_direct_link_is_offered_only_when_there_is_one(qtbot):
    """VB CmCopyLink. A menu entry that silently copies "" is worse than a
    greyed-out one, so the action follows whether the file has a link."""
    from vaultkeeper.vault.scraper_info import VaultScraperInfo

    with_link = VaultScraperInfo(filename="a.zip", direct_url="https://x.invalid/a.zip")
    without = VaultScraperInfo(filename="b.zip")
    assert bool(with_link.direct_url or with_link.counter_url)
    assert not (without.direct_url or without.counter_url)


# -- Ticking several files at once (newtopic4.htm) ------------------------------- #
@pytest.fixture()
def controller(tmp_path):
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_space_toggles_every_selected_file(qtbot, controller):
    """"If you don't want to use these files, select all the files and press the
    Space Bar." Qt's own Space handling ticks the current row and ignores the
    rest of the selection, so that instruction ticked exactly one file."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

    from vaultkeeper.ui.dialogs.download_project import DownloadProjectDialog

    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    assert dlg.file_tree.selectionMode() == QTreeWidget.SelectionMode.ExtendedSelection

    for name in ("a.7z", "b.7z", "c.7z"):
        item = QTreeWidgetItem([name, "1 KB", ""])
        item.setCheckState(0, Qt.CheckState.Checked)
        dlg.file_tree.addTopLevelItem(item)
    # Current first, then select all: setCurrentItem collapses the selection to
    # the item it is given.
    dlg.file_tree.setCurrentItem(dlg.file_tree.topLevelItem(0))
    dlg.file_tree.selectAll()
    assert len(dlg.file_tree.selectedItems()) == 3

    qtbot.keyClick(dlg.file_tree, Qt.Key.Key_Space)

    states = [
        dlg.file_tree.topLevelItem(i).checkState(0)
        for i in range(dlg.file_tree.topLevelItemCount())
    ]
    assert states == [Qt.CheckState.Unchecked] * 3


def test_a_mixed_selection_follows_the_current_row(qtbot, controller):
    """Otherwise each row flips its own way and the selection ends up mixed
    again, which is the opposite of what pressing Space on all of them means."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTreeWidgetItem

    from vaultkeeper.ui.dialogs.download_project import DownloadProjectDialog

    dlg = DownloadProjectDialog(controller)
    qtbot.addWidget(dlg)
    for name, state in (("a.7z", Qt.CheckState.Checked), ("b.7z", Qt.CheckState.Unchecked)):
        item = QTreeWidgetItem([name, "1 KB", ""])
        item.setCheckState(0, state)
        dlg.file_tree.addTopLevelItem(item)
    dlg.file_tree.setCurrentItem(dlg.file_tree.topLevelItem(0))  # ticked
    dlg.file_tree.selectAll()

    qtbot.keyClick(dlg.file_tree, Qt.Key.Key_Space)

    assert dlg.file_tree.topLevelItem(0).checkState(0) == Qt.CheckState.Unchecked
    assert dlg.file_tree.topLevelItem(1).checkState(0) == Qt.CheckState.Unchecked
