"""Installer-file operations in the Details view (VB ``NIT.DetailsView``).

MoveToFolder reinstalls an installed mod after the move and rebuilds its patch
INI; RemoveInstallerFiles recycles the file and anneals the mods sharing it.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.hak_patch import patch_ini_haks
from vaultkeeper.ui.controller import ProfileController


def _open(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _mod(c: ProfileController, name: str, folder: str, filename: str, data: bytes) -> None:
    c.create_mod(name)
    payload = c.ctx.profile_mods_dir / name / C.MOD_INSTALLER_DIR / folder
    payload.mkdir(parents=True)
    (payload / filename).write_bytes(data)
    c.create_installer(name)


def test_moving_a_hak_to_patch_reinstalls_the_mod(tmp_path: Path) -> None:
    c = _open(tmp_path)
    _mod(c, "Haks", "hak", "p.hak", b"H")
    c.install(["Haks"])

    result = c.move_mod_files("Haks", "hak", ["p.hak"], "patch")

    assert result["ok"]
    assert c.pd.mod_item("Haks").installed
    assert (c.ctx.game_folders["patch"] / "p.hak").is_file()
    assert not (c.ctx.game_folders["hak"] / "p.hak").exists()
    root = c.ctx.profile_mods_dir / "Haks" / C.MOD_INSTALLER_DIR / C.MOD_ROOT_FOLDER
    assert patch_ini_haks(root / C.USER_PATCH_INI_FILE) == ["p"]
    assert patch_ini_haks(c.patch_ini_path) == ["p"]


def test_deleting_an_installer_file_recycles_it(
    tmp_path: Path, recycle_bin: Path
) -> None:
    c = _open(tmp_path)
    _mod(c, "Alpha", "override", "x.2da", b"alpha")
    _mod(c, "Beta", "override", "x.2da", b"beta")
    c.install(["Alpha", "Beta"])
    ifk = FileKeyInfo.installed("override", "x.2da")
    winner = c.pd.installed_item(ifk).installer
    other = "Alpha" if winner == "Beta" else "Beta"

    assert c.delete_mod_file(winner, "override", "x.2da")

    assert any(recycle_bin.iterdir())
    assert FileKeyInfo(c.pd.mod_item(winner).group, winner, "override", "x.2da") not in (
        c.pd.file_list
    )
    # As in NIT: the game copy no longer matches any mod's (anneal skips it).
    assert c.pd.installed_item(ifk).installer == C.INSTALLER_UNKNOWN
    assert other in [m.mod_name for m in c.pd.installed_item(ifk).mod_file_conflicts]
