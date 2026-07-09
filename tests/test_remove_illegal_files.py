"""Tests for Remove Illegal Mod Files (VB ``ProfileData.RemoveIllegalModFiles``).

An installer file is illegal when its folder is not a mapped NWN folder or its
extension is not an NWN extension. Illegal whole folders move to the mod's
``.Removed Items`` area; extension-illegal files in a legal folder move
individually; all are dropped from the database.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.create_mod("Mod")
    return controller


def _installer(controller: ProfileController) -> Path:
    return controller.ctx.profile_mods_dir / "Mod" / C.MOD_INSTALLER_DIR


def test_no_illegal_files_reports_none(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    inst = _installer(controller)
    (inst / "hak").mkdir(parents=True)
    (inst / "hak" / "good.hak").write_bytes(b"H")
    controller.pd.scan_mod_files(controller.pd.mod_item("Mod"), controller.ctx.profile_mods_dir)
    result = controller.remove_illegal_mod_files()
    assert result == {"folders": 0, "files": 0, "message": "Illegal Mod items removed: None."}
    assert (inst / "hak" / "good.hak").is_file()


def test_illegal_folder_moved_to_removed_items(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    inst = _installer(controller)
    # "junk" is not a legal mapped folder → whole folder is illegal.
    (inst / "junk").mkdir(parents=True)
    (inst / "junk" / "a.hak").write_bytes(b"H")
    (inst / "junk" / "b.hak").write_bytes(b"H")
    controller.pd.scan_mod_files(controller.pd.mod_item("Mod"), controller.ctx.profile_mods_dir)

    result = controller.remove_illegal_mod_files()
    assert result["folders"] == 1
    removed = controller.ctx.profile_mods_dir / "Mod" / C.REMOVED_ITEMS_DIR / "junk"
    assert (removed / "a.hak").is_file() and (removed / "b.hak").is_file()
    assert not (inst / "junk").exists()
    # Both keys dropped from the DB.
    assert all(fk.folder != "junk" for fk in controller.pd.mod_item("Mod").files)


def test_extension_illegal_file_moved_individually(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    inst = _installer(controller)
    # A legal folder (hak) but a non-NWN extension file → file illegal, folder ok.
    (inst / "hak").mkdir(parents=True)
    (inst / "hak" / "keep.hak").write_bytes(b"H")
    (inst / "hak" / "junk.xyz").write_bytes(b"X")
    controller.pd.scan_mod_files(controller.pd.mod_item("Mod"), controller.ctx.profile_mods_dir)

    result = controller.remove_illegal_mod_files()
    assert result == {
        "folders": 0,
        "files": 1,
        "message": "Illegal Mod items removed. Folders: None. Files: 1.",
    }
    assert (inst / "hak" / "keep.hak").is_file()  # legal file untouched
    assert not (inst / "hak" / "junk.xyz").exists()
    moved = controller.ctx.profile_mods_dir / "Mod" / C.REMOVED_ITEMS_DIR / "hak" / "junk.xyz"
    assert moved.is_file()
    filenames = {fk.filename for fk in controller.pd.mod_item("Mod").files}
    assert "junk.xyz" not in filenames and "keep.hak" in filenames
