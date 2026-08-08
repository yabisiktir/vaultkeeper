"""Tests for the installation report + Installation Analyser dialog."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.installation_analyser import InstallationAnalyser


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_installation_report_flags_issues(qtbot, tmp_path):
    controller = _controller(tmp_path)
    # A changed game original (pristine CRC 100, installed CRC differs).
    orig = FileKeyInfo.installed("hak", "orig.hak")
    controller.pd.original_files[orig.file_key] = 100
    controller.pd.add_installed(
        InstalledFileData(
            key=orig, installer=C.INSTALLER_ORIGINAL, file_crc=999, extension=".hak"
        )
    )
    # An unknown-source installed file with a mapped extension.
    myst = FileKeyInfo.installed("hak", "myst.hak")
    controller.pd.add_installed(
        InstalledFileData(key=myst, installer=C.INSTALLER_UNKNOWN, extension=".hak")
    )

    report = controller.installation_report()
    assert report["changed_originals"] == 1
    assert report["unknown_source"] == 1
    categories = {i["category"] for i in report["issues"]}
    assert categories == {"Changed original", "Unknown source"}


def test_analyser_dialog_populates(qtbot, tmp_path):
    controller = _controller(tmp_path)
    myst = FileKeyInfo.installed("hak", "myst.hak")
    controller.pd.add_installed(
        InstalledFileData(key=myst, installer=C.INSTALLER_UNKNOWN, extension=".hak")
    )
    dlg = InstallationAnalyser.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 1
    assert dlg.table.topLevelItem(0).text(0) == "Unknown source"


def test_clean_installation_no_issues(qtbot, tmp_path):
    report = _controller(tmp_path).installation_report()
    assert report["issues"] == []
    assert report["changed_originals"] == 0


# -- Installation browser (VB LvFolders → LvFiles) ------------------------- #


def test_browser_report_groups_by_folder(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.pd.add_installed(
        InstalledFileData(
            key=FileKeyInfo.installed("hak", "a.hak"),
            installer="CEP",
            byte_size=100,
            extension=".hak",
        )
    )
    controller.pd.add_installed(
        InstalledFileData(
            key=FileKeyInfo.installed("hak", "b.hak"),
            installer="Music",
            byte_size=50,
            extension=".hak",
        )
    )
    controller.pd.add_installed(
        InstalledFileData(
            key=FileKeyInfo.installed("tlk", "c.tlk"),
            installer="CEP",
            byte_size=25,
            extension=".tlk",
        )
    )
    report = controller.installation_browser_report()
    by_name = {f["name"]: f for f in report["folders"]}
    assert by_name["hak"]["count"] == 2
    assert by_name["tlk"]["count"] == 1
    assert report["total_bytes"] == 175
    # Sources are surfaced per file.
    sources = {f["source"] for f in by_name["hak"]["files"]}
    assert sources == {"CEP", "Music"}


def test_browser_dialog_populates(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.pd.add_installed(
        InstalledFileData(
            key=FileKeyInfo.installed("hak", "a.hak"),
            installer="CEP",
            byte_size=100,
            extension=".hak",
        )
    )
    dlg = InstallationAnalyser.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.folders.count() == 1
    # Selecting the folder shows its files.
    assert dlg.files.topLevelItemCount() == 1
    assert dlg.files.topLevelItem(0).text(1) == "CEP"
    assert "Total installed size" in dlg.total.text()


# -- Refresh + Select (VB BtRefresh / BtSelect) ---------------------------- #


def test_analyser_refresh_picks_up_new_installs(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.pd.add_installed(
        InstalledFileData(
            key=FileKeyInfo.installed("hak", "a.hak"), installer="CEP",
            byte_size=100, extension=".hak",
        )
    )
    dlg = InstallationAnalyser.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.folders.count() == 1

    # A new install appears in a different folder; Refresh surfaces it.
    controller.pd.add_installed(
        InstalledFileData(
            key=FileKeyInfo.installed("tlk", "c.tlk"), installer="CEP",
            byte_size=25, extension=".tlk",
        )
    )
    dlg.refresh()
    assert dlg.folders.count() == 2


def test_analyser_select_jumps_to_file_mod(qtbot, tmp_path):
    controller = _controller(tmp_path)
    controller.pd.add_installed(
        InstalledFileData(
            key=FileKeyInfo.installed("hak", "a.hak"), installer="CEP",
            byte_size=100, extension=".hak",
        )
    )
    picked = []
    dlg = InstallationAnalyser.show_for(controller, picked.append)
    qtbot.addWidget(dlg)
    dlg.files.setCurrentItem(dlg.files.topLevelItem(0))
    dlg._on_select_mod()
    assert picked == ["CEP"]
    assert not dlg.isVisible()  # closes after select


# --------------------------------------------------------------------------- #
# Reaching the file (VB CmOpenFolder / CmProperties)
# --------------------------------------------------------------------------- #
def test_browser_rows_carry_the_installed_path(tmp_path):
    """Open Folder and Properties both need the file's real location."""
    from vaultkeeper.ui.controller import ProfileController

    profile_mods = tmp_path / "Profiles" / "P"
    (profile_mods / "Alpha" / ".Mod Installer" / "hak").mkdir(parents=True)
    game = tmp_path / "NWN"
    (game / "hak").mkdir(parents=True)
    (game / "hak" / "a.hak").write_bytes(b"HAK")

    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game,
        store_path=tmp_path / "Data" / "P.json",
    )
    report = controller.installation_browser_report()
    files = [f for folder in report["folders"] for f in folder["files"]]
    # Whatever was picked up, every row must expose where it lives (or "" when
    # the folder is not one we resolved) rather than omitting the key.
    assert all("path" in f for f in files)
