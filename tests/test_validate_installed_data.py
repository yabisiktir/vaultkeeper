"""Tests for Validate Installed Data (VB MsValidateInstalledData / CheckInstalledFiles)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _make_and_install(controller: ProfileController, tmp_path: Path, name: str) -> Path:
    controller.create_mod(name)
    payload = (
        tmp_path / "Profiles" / "P" / name / C.MOD_INSTALLER_DIR / "override" / f"{name}.2da"
    )
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"DATA")
    controller.build_installer_payload(name)
    controller.install([name])
    return payload


def test_validate_is_stable_once_settled(tmp_path: Path) -> None:
    # The first validate may absorb freshly-generated game files (e.g. nwnpatch.ini);
    # a second validate with nothing changed reports no problems.
    controller = _controller(tmp_path)
    _make_and_install(controller, tmp_path, "Alpha")
    controller.validate_installed_data()
    msg = controller.validate_installed_data()
    assert "None" in msg


def test_validate_drops_record_for_vanished_game_file(tmp_path: Path) -> None:
    from vaultkeeper.core.file_key import FileKeyInfo

    controller = _controller(tmp_path)
    _make_and_install(controller, tmp_path, "Alpha")

    # The installed record for the payload exists.
    key = FileKeyInfo.installed("override", "Alpha.2da")
    assert key in controller.pd.installed_list

    # Delete the file from the game folder behind NIT's back.
    override = controller.ctx.game_folders["override"]
    for f in override.glob("*.2da"):
        f.unlink()

    msg = controller.validate_installed_data()
    # The vanished record is repaired away.
    assert key not in controller.pd.installed_list
    assert "Missing files removed" in msg


def test_check_installed_files_counts(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _make_and_install(controller, tmp_path, "Alpha")
    override = controller.ctx.game_folders["override"]
    for f in override.glob("*.2da"):
        f.unlink()
    result = controller.pd.check_installed_files(
        controller.ctx.game_folders, root_folder_name=controller.ctx.root_folder_name
    )
    assert result["removed"] >= 1
