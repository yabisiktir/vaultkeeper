"""Tests for the conflicts report + viewer dialog."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.conflicts_viewer import ConflictsViewer


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _add_conflict(controller, filename, winner, mods):
    ik = FileKeyInfo.installed("hak", filename)
    ifd = InstalledFileData(key=ik, installer=winner)
    for group, mod in mods:
        ifd.mod_file_conflicts.append(FileKeyInfo.mod_file(group, mod, f"hak\\{filename}"))
    controller.pd.add_installed(ifd)


def test_conflicts_report_lists_multi_mod_files(tmp_path):
    controller = _controller(tmp_path)
    _add_conflict(controller, "cep.hak", "Mod Two", [("A", "Mod One"), ("B", "Mod Two")])
    # A file with a single claimant is not a conflict.
    ik = FileKeyInfo.installed("hak", "solo.hak")
    solo = InstalledFileData(key=ik, installer="Mod One")
    solo.mod_file_conflicts.append(FileKeyInfo.mod_file("A", "Mod One", "hak\\solo.hak"))
    controller.pd.add_installed(solo)

    report = controller.conflicts_report()
    assert report["count"] == 1
    row = report["rows"][0]
    assert row["file"] == f"hak{C.FILEKEY_SEPARATOR}cep.hak"
    assert row["winner"] == "Mod Two"
    assert row["mods"] == ["Mod One", "Mod Two"]


def test_conflicts_viewer_populates(qtbot, tmp_path):
    controller = _controller(tmp_path)
    _add_conflict(controller, "cep.hak", "Mod Two", [("A", "Mod One"), ("B", "Mod Two")])
    dlg = ConflictsViewer.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 1
    item = dlg.table.topLevelItem(0)
    assert item.text(1) == "Mod Two"
    # The "others" column excludes the winner.
    assert item.text(2) == "Mod One"


def test_no_conflicts(qtbot, tmp_path):
    controller = _controller(tmp_path)
    report = controller.conflicts_report()
    assert report["count"] == 0
    dlg = ConflictsViewer.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 0
