"""Validate Mods resyncs mods and installer files with disk (VB ``ValidateModAndFileData``).

Logic audit stage 4, ProfileData: NIT's Validate Mods first adds mod folders and
installer files the database does not know, forgets records of deleted files and
re-links records to their mods; Vaultkeeper's pass did none of it.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _payload(controller: ProfileController, mod: str, name: str, data: bytes = b"DATA") -> Path:
    path = controller.ctx.profile_mods_dir / mod / C.MOD_INSTALLER_DIR / "override" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_a_new_mod_folder_joins_ungrouped_with_its_files(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _payload(controller, "Dropped In", "a.2da")

    message = controller.validate_mods()

    md = controller.pd.mod_item("Dropped In")
    assert md is not None and md.group == C.GROUP_NONE
    assert [fk.filename for fk in md.files if fk.folder != C.MOD_NIT_DIR] == ["a.2da"]
    assert "Mods added: 1" in message


def test_a_new_installer_file_is_added_and_checksummed(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Mod")
    _payload(controller, "Mod", "a.2da")
    controller.create_installer("Mod")
    _payload(controller, "Mod", "b.2da", b"MORE")

    controller.validate_mods()

    md = controller.pd.mod_item("Mod")
    names = sorted(fk.filename for fk in md.files if fk.folder != C.MOD_NIT_DIR)
    assert names == ["a.2da", "b.2da"]
    fk = next(fk for fk in md.files if fk.filename == "b.2da")
    assert controller.pd.file_list[fk].file_crc != 0


def test_a_deleted_installer_file_is_forgotten(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Mod")
    _payload(controller, "Mod", "a.2da")
    gone = _payload(controller, "Mod", "b.2da")
    controller.create_installer("Mod")
    gone.unlink()

    message = controller.validate_mods()

    md = controller.pd.mod_item("Mod")
    assert "b.2da" not in [fk.filename for fk in md.files]
    assert not any(fk.filename == "b.2da" for fk in controller.pd.file_list)
    assert "removed: 1" in message


def test_a_mod_without_a_folder_is_kept_with_its_records(tmp_path: Path) -> None:
    # DELIBERATE: NIT removes it; an imported profile's mods have no folder.
    controller = _controller(tmp_path)
    controller.create_mod("Imported")
    fk = FileKeyInfo(C.GROUP_NONE, "Imported", "override", "x.2da")
    md = controller.pd.mod_item("Imported")
    md.files.append(fk)
    controller.pd.rescan_installed_state(
        controller.ctx.game_folders, root_folder_name=controller.ctx.root_folder_name
    )
    folder = controller.ctx.profile_mods_dir / "Imported"
    if folder.exists():
        import shutil

        shutil.rmtree(folder)

    controller.validate_mods()

    assert controller.pd.mod_item("Imported") is not None
    assert fk in controller.pd.file_list


def test_a_game_copy_without_a_checksum_does_not_read_as_overridden(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("Mod")
    _payload(controller, "Mod", "a.2da")
    controller.create_installer("Mod")
    controller.install(["Mod"])
    assert controller.pd.mod_item("Mod").mod_state == State.INSTALLED
    # Records carried over with no checksums on either side.
    for fd in controller.pd.file_list.values():
        fd.file_crc = 0
    for ifd in controller.pd.installed_list.values():
        ifd.file_crc = 0

    controller.validate_mods()

    assert controller.pd.mod_item("Mod").mod_state == State.INSTALLED
