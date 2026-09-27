"""Patch-hak order and patch INI names (VB ``HakPatchManager``), logic audit stage 4.

The patch INI's order decides which patch hak wins. The controller built its
manager without the saved order, so every install after a restart rewrote the
INI alphabetically. NIT also seeds the order from the existing INI, scans the
patch folder on disk, rebuilds the INI on load when new patch haks appear, and
names a mod's patch INI after the edition (userpatch.ini on EE).
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.hak_patch import patch_ini_haks, read_patch_sequence
from vaultkeeper.ui.controller import ProfileController


def _open(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _patch_mod(c: ProfileController, name: str, hak: str) -> None:
    c.create_mod(name)
    payload = c.ctx.profile_mods_dir / name / C.MOD_INSTALLER_DIR / "patch"
    payload.mkdir(parents=True)
    (payload / f"{hak}.hak").write_bytes(hak.encode())
    c.create_installer(name)


def test_installs_after_a_restart_keep_the_saved_order(tmp_path: Path) -> None:
    c = _open(tmp_path)
    _patch_mod(c, "Zeta Mod", "zeta")
    _patch_mod(c, "Alpha Mod", "alpha")
    c.install(["Zeta Mod", "Alpha Mod"])
    c.save_patch_hak_sequence(["zeta", "alpha"])
    c.uninstall(["Alpha Mod"])
    c.save()

    c = _open(tmp_path)  # a new session: nothing opened the Hak Patch editor
    c.install(["Alpha Mod"])

    assert patch_ini_haks(c.patch_ini_path) == ["zeta", "alpha"]


def test_the_first_order_comes_from_the_existing_patch_ini(tmp_path: Path) -> None:
    c = _open(tmp_path)
    patch = c.ctx.game_folders["patch"]
    patch.mkdir(parents=True, exist_ok=True)
    for hak in ("aaa", "bbb"):
        (patch / f"{hak}.hak").write_bytes(b"H")
    c.patch_ini_path.write_text("[Patch]\nPatchFile000=bbb\nPatchFile001=aaa\n")

    assert c.patch_hak_sequence() == ["bbb", "aaa"]
    assert read_patch_sequence(c._profile_data_dir()) == ["bbb", "aaa"]


def test_a_new_patch_hak_is_added_to_the_ini_when_the_profile_opens(tmp_path: Path) -> None:
    c = _open(tmp_path)
    c.save_patch_hak_sequence([])
    c.save()
    patch = c.ctx.game_folders["patch"]
    patch.mkdir(parents=True, exist_ok=True)
    (patch / "dropped.hak").write_bytes(b"H")

    c = _open(tmp_path)

    assert patch_ini_haks(c.patch_ini_path) == ["dropped"]


def test_a_hak_whose_file_is_gone_is_not_listed(tmp_path: Path) -> None:
    c = _open(tmp_path)
    _patch_mod(c, "Mod", "gone")
    c.install(["Mod"])
    (c.ctx.game_folders["patch"] / "gone.hak").unlink()

    c._hpm.create_nwn_patch_ini_file()

    assert patch_ini_haks(c.patch_ini_path) == []


def test_a_mod_patch_ini_takes_the_edition_name(tmp_path: Path) -> None:
    # EE: a shipped nwnpatch.ini becomes userpatch.ini, in the build and in Validate.
    c = _open(tmp_path)
    c.create_mod("Patch Pack")
    downloads = c.ctx.profile_mods_dir / "Patch Pack"
    (downloads / "nwnpatch.ini").write_text("[Patch]\nPatchFile000=p\n")
    (downloads / "p.hak").write_bytes(b"H")
    c.rebuild_installer("Patch Pack")
    root = c.ctx.profile_mods_dir / "Patch Pack" / C.MOD_INSTALLER_DIR / C.MOD_ROOT_FOLDER
    assert (root / C.USER_PATCH_INI_FILE).is_file()
    assert not (root / C.PATCH_INI_FILE).exists()
    installer = c.ctx.profile_mods_dir / "Patch Pack" / C.MOD_INSTALLER_DIR
    assert (installer / "patch" / "p.hak").is_file()

    (root / C.USER_PATCH_INI_FILE).rename(root / C.PATCH_INI_FILE)
    c.validate_mods()
    assert (root / C.USER_PATCH_INI_FILE).is_file()
    assert not (root / C.PATCH_INI_FILE).exists()
