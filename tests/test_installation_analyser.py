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
