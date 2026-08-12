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


def test_selecting_a_large_folder_stays_fast(qtbot):
    """A row must carry its own data, not the folder holding every other row.

    Attaching the folder dict to each item — which this briefly did, to reach
    it from the Properties action — hands PySide6 a structure containing every
    file in the folder and it converts the whole thing once per row. On the
    owner's 6,392-file override folder that took 40 seconds and looked like a
    freeze; the row alone takes a fraction of a second.

    Asserted as a shape, not a stopwatch: no row may reference a container of
    other rows, which is the property that made it quadratic.
    """
    from types import SimpleNamespace

    from vaultkeeper.ui.dialogs.installation_analyser import (
        _FILE_ROLE,
        InstallationAnalyser,
    )

    count = 400
    files = [
        {"filename": f"f{i}.tga", "source": "M", "size": "1 KB",
         "modified": "01 Jan 2026", "path": f"/x/f{i}.tga"}
        for i in range(count)
    ]
    browser = {
        "folders": [
            {"name": "override", "count": count, "size": "1 MB",
             "size_bytes": 1, "files": files}
        ],
        "total_size": "1 MB",
    }
    controller = SimpleNamespace(
        installation_report=lambda: {"rows": [], "summary": "", "counts": {}},
        installation_browser_report=lambda: browser,
    )
    dlg = InstallationAnalyser(controller)
    qtbot.addWidget(dlg)
    dlg._on_folder(0)
    assert dlg.files.topLevelItemCount() == count

    stored = dlg.files.topLevelItem(0).data(0, _FILE_ROLE)
    assert stored["filename"] == "f0.tga"
    assert "path" in stored, "Properties and Open Folder need the path"
    for value in stored.values():
        assert not isinstance(value, (list, dict)), (
            f"a row must not carry a collection ({value!r:.40}) — that is what "
            "made selecting a large folder quadratic"
        )


# -- double-click does the row's own action (VB LvFiles / LvFolders) ----------- #
def test_double_clicking_a_file_shows_its_properties(qtbot, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from vaultkeeper.ui.dialogs.installation_analyser import InstallationAnalyser

    target = tmp_path / "a.hak"
    target.write_bytes(b"x")
    browser = {
        "folders": [
            {
                "name": "hak",
                "count": 1,
                "size": "1 KB",
                "size_bytes": 1,
                "files": [
                    {"filename": "a.hak", "source": "Mod", "size": "1 KB",
                     "modified": "", "path": str(target)}
                ],
            }
        ],
        "total_size": "1 KB",
    }
    controller = SimpleNamespace(
        installation_report=lambda: {"rows": [], "summary": "", "counts": {}},
        installation_browser_report=lambda: browser,
    )
    dlg = InstallationAnalyser(controller)
    qtbot.addWidget(dlg)
    dlg._on_folder(0)

    shown = []
    monkeypatch.setattr(dlg, "_on_file_properties", lambda: shown.append(1))
    dlg.files.itemDoubleClicked.emit(dlg.files.topLevelItem(0), 0)
    assert shown == [1]


def test_double_clicking_a_folder_opens_it(qtbot, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from vaultkeeper.ui.dialogs.installation_analyser import InstallationAnalyser

    browser = {
        "folders": [
            {"name": "hak", "count": 0, "size": "0", "size_bytes": 0, "files": []}
        ],
        "total_size": "0",
    }
    controller = SimpleNamespace(
        installation_report=lambda: {"rows": [], "summary": "", "counts": {}},
        installation_browser_report=lambda: browser,
    )
    dlg = InstallationAnalyser(controller)
    qtbot.addWidget(dlg)

    opened = []
    monkeypatch.setattr(dlg, "_on_open_folder", lambda: opened.append(1))
    dlg.folders.itemDoubleClicked.emit(dlg.folders.item(0))
    assert opened == [1]


def test_original_files_on_disk_are_listed_with_no_source(tmp_path, qtbot):
    """bhinstallationanalyser.htm: the Analyser shows what is in the folders,
    not only what a profile installed — so an original .nwm can be selected."""
    controller = _controller(tmp_path)
    nwm_dir = controller.ctx.game_folders["nwm"]
    nwm_dir.mkdir(parents=True, exist_ok=True)
    (nwm_dir / "Prelude.nwm").write_bytes(b"MODULE")

    report = controller.installation_browser_report()
    by_name = {f["name"]: f for f in report["folders"]}
    assert "nwm" in by_name
    row = by_name["nwm"]["files"][0]
    assert row["filename"] == "Prelude.nwm"
    assert row["source"] == ""  # nothing in this profile installed it


def test_convert_button_shows_only_for_a_selected_nwm(tmp_path, qtbot):
    """newtopic59.htm: "displays a Convert button when a NWM file is selected"."""
    controller = _controller(tmp_path)
    for folder in ("nwm", "hak"):
        (controller.ctx.game_folders[folder]).mkdir(parents=True, exist_ok=True)
    (controller.ctx.game_folders["nwm"] / "Prelude.nwm").write_bytes(b"M")
    (controller.ctx.game_folders["hak"] / "thing.hak").write_bytes(b"H")

    dlg = InstallationAnalyser(controller)
    qtbot.addWidget(dlg)
    assert not dlg._convert_button.isVisibleTo(dlg)

    # Select the nwm folder, then its file.
    for row in range(dlg.folders.count()):
        if dlg.folders.item(row).text().startswith("nwm"):
            dlg.folders.setCurrentRow(row)
            break
    dlg.files.setCurrentItem(dlg.files.topLevelItem(0))
    assert dlg._convert_button.isVisibleTo(dlg)

    # A hak is not convertible.
    for row in range(dlg.folders.count()):
        if dlg.folders.item(row).text().startswith("hak"):
            dlg.folders.setCurrentRow(row)
            break
    dlg.files.setCurrentItem(dlg.files.topLevelItem(0))
    assert not dlg._convert_button.isVisibleTo(dlg)


def test_convert_button_calls_the_controller(tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    controller = _controller(tmp_path)
    (controller.ctx.game_folders["nwm"]).mkdir(parents=True, exist_ok=True)
    (controller.ctx.game_folders["nwm"] / "Prelude.nwm").write_bytes(b"M")

    selected = []
    dlg = InstallationAnalyser(controller, on_select=selected.append)
    qtbot.addWidget(dlg)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    called = {}

    def fake_convert(path):
        called["path"] = path
        return {"ok": True, "mod_name": "Prelude", "message": "done"}

    monkeypatch.setattr(controller, "convert_nwm_to_mod", fake_convert)
    for row in range(dlg.folders.count()):
        if dlg.folders.item(row).text().startswith("nwm"):
            dlg.folders.setCurrentRow(row)
            break
    dlg.files.setCurrentItem(dlg.files.topLevelItem(0))
    dlg._on_convert_nwm()

    assert called["path"].name == "Prelude.nwm"
    assert selected == ["Prelude"]  # the converted mod is selected in the window
