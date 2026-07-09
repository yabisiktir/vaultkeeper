"""Tests for Create Missing Installers (VB ``CreateMissingInstallers``).

Controller side: which mods count as "missing" (no ``.Mod Installer`` folder),
the persisted exclude list round-trip, and building the selected installers.
Dialog side: population honours exclusions + the include-excluded toggle, and
Create builds + persists.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    return controller


def _mod_without_installer(controller: ProfileController, name: str) -> None:
    """Create a mod DB row and folder but remove its .Mod Installer dir."""
    controller.create_mod(name)
    installer = controller.ctx.profile_mods_dir / name / C.MOD_INSTALLER_DIR
    for child in sorted(installer.rglob("*"), reverse=True):
        child.rmdir() if child.is_dir() else child.unlink()
    installer.rmdir()


# -- Controller ------------------------------------------------------------- #


def test_mods_missing_installer_lists_only_folderless(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Has Installer")  # create_mod makes .Mod Installer
    _mod_without_installer(controller, "No Installer")
    assert controller.mods_missing_installer() == ["No Installer"]


def test_missing_report_prunes_stale_exclusions(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _mod_without_installer(controller, "Alpha")
    _mod_without_installer(controller, "Beta")
    # Exclude Alpha and a stale name no longer missing.
    controller.save_missing_installer_excludes(["Alpha", "Ghost"])
    report = controller.missing_installer_report()
    assert set(report["mods"]) == {"Alpha", "Beta"}
    assert report["excluded"] == ["Alpha"]  # Ghost pruned (not missing)


def test_exclude_list_round_trip(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.save_missing_installer_excludes(["One", "Two"])
    assert controller._read_missing_installer_excludes() == ["One", "Two"]


def test_create_missing_installers_builds_folder(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _mod_without_installer(controller, "Alpha")
    (controller.ctx.profile_mods_dir / "Alpha" / "content.hak").write_bytes(b"H")
    result = controller.create_missing_installers(["Alpha"])
    assert result["built"] == 1
    installer = controller.ctx.profile_mods_dir / "Alpha" / C.MOD_INSTALLER_DIR
    assert (installer / "hak" / "content.hak").is_file()
    assert controller.pd.mod_item("Alpha").is_installer()
    # No longer missing.
    assert controller.mods_missing_installer() == []


# -- Dialog ----------------------------------------------------------------- #


def test_dialog_hides_excluded_until_toggled(tmp_path: Path, qtbot) -> None:
    from vaultkeeper.ui.dialogs.create_missing_installers import CreateMissingInstallers

    controller = _controller(tmp_path)
    _mod_without_installer(controller, "Alpha")
    _mod_without_installer(controller, "Beta")
    controller.save_missing_installer_excludes(["Beta"])

    dialog = CreateMissingInstallers(controller)
    qtbot.addWidget(dialog)
    shown = {dialog._tree.topLevelItem(i).text(0) for i in range(dialog._tree.topLevelItemCount())}
    assert shown == {"Alpha"}  # Beta hidden (excluded)

    dialog._include_excluded.setChecked(True)
    shown = {dialog._tree.topLevelItem(i).text(0) for i in range(dialog._tree.topLevelItemCount())}
    assert shown == {"Alpha", "Beta"}


def test_dialog_create_builds_and_persists(tmp_path: Path, qtbot) -> None:
    from vaultkeeper.ui.dialogs.create_missing_installers import CreateMissingInstallers

    controller = _controller(tmp_path)
    _mod_without_installer(controller, "Alpha")
    _mod_without_installer(controller, "Beta")
    (controller.ctx.profile_mods_dir / "Alpha" / "a.hak").write_bytes(b"H")

    dialog = CreateMissingInstallers(controller)
    qtbot.addWidget(dialog)
    # Uncheck Beta so only Alpha is built; Beta becomes an exclusion.
    for i in range(dialog._tree.topLevelItemCount()):
        item = dialog._tree.topLevelItem(i)
        if item.text(0) == "Beta":
            from PySide6.QtCore import Qt

            item.setCheckState(0, Qt.CheckState.Unchecked)
    dialog._on_create()

    assert controller.pd.mod_item("Alpha").is_installer()
    assert not controller.pd.mod_item("Beta").is_installer()
    assert controller._read_missing_installer_excludes() == ["Beta"]
