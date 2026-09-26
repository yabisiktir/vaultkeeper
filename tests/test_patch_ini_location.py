"""Which file lists the installed patch haks (VB ``Paths.NwnPatchIniFile``).

Enhanced Edition reads a user's patch haks from ``userpatch.ini`` in the user
files folder; its install folder ships ``nwnpatch.ini``, which NIT never writes
on EE. Vaultkeeper wrote ``<install>/nwnpatch.ini`` for every edition (logic
audit, docs/logic_audit/stage2_findings.md S1).
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, *, is_ee: bool) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "install",
        store_path=tmp_path / "Data" / "P.json",
        is_ee=is_ee,
        game_user_dir=(tmp_path / "user") if is_ee else None,
    )


def _install_patch_hak(c: ProfileController, tmp_path: Path) -> None:
    c.create_mod("Delta Patch")
    hak = tmp_path / "Profiles" / "P" / "Delta Patch" / "patch" / "delta.hak"
    hak.parent.mkdir(parents=True, exist_ok=True)
    hak.write_bytes(b"HAK")
    c.build_installer_payload("Delta Patch")
    c.install(["Delta Patch"])


def test_ee_patch_haks_go_to_userpatch_ini_in_the_user_folder(tmp_path: Path) -> None:
    install = tmp_path / "install"
    install.mkdir()
    shipped = install / C.PATCH_INI_FILE
    shipped.write_text("[Patch]\nPatchFile000=the_game_s_own\n")
    c = _controller(tmp_path, is_ee=True)

    _install_patch_hak(c, tmp_path)

    assert c.patch_ini_path == tmp_path / "user" / C.USER_PATCH_INI_FILE
    assert "PatchFile000=delta" in c.patch_ini_path.read_text()
    # The game's own file is left exactly as shipped, with no backup made.
    assert shipped.read_text() == "[Patch]\nPatchFile000=the_game_s_own\n"
    assert not (install / "nwnpatch.ini.bak").exists()


def test_classic_profile_keeps_nwnpatch_ini_in_the_install_folder(tmp_path: Path) -> None:
    c = _controller(tmp_path, is_ee=False)

    _install_patch_hak(c, tmp_path)

    assert c.patch_ini_path == tmp_path / "install" / C.PATCH_INI_FILE
    assert "PatchFile000=delta" in c.patch_ini_path.read_text()


def test_ee_install_patch_ini_replaced_by_an_older_version_is_restored(tmp_path: Path) -> None:
    install = tmp_path / "install"
    install.mkdir()
    (install / C.PATCH_INI_FILE).write_text("[Patch]\nPatchFile000=written_by_old_vaultkeeper\n")
    (install / "nwnpatch.ini.bak").write_text("[Patch]\nPatchFile000=the_game_s_own\n")

    _controller(tmp_path, is_ee=True)

    assert (install / C.PATCH_INI_FILE).read_text() == "[Patch]\nPatchFile000=the_game_s_own\n"
    assert not (install / "nwnpatch.ini.bak").exists()


def test_ee_install_patch_ini_without_a_backup_is_left_alone(tmp_path: Path) -> None:
    install = tmp_path / "install"
    install.mkdir()
    (install / C.PATCH_INI_FILE).write_text("[Patch]\nPatchFile000=unknown_origin\n")

    _controller(tmp_path, is_ee=True)

    assert (install / C.PATCH_INI_FILE).read_text() == "[Patch]\nPatchFile000=unknown_origin\n"


def test_ee_profile_without_a_named_user_folder_never_writes_outside_its_game_root(
    tmp_path: Path,
) -> None:
    # No explicit user folder: the EE split is off, and the auto-detected default
    # (a real game folder on a real machine) must not be written to.
    c = ProfileController.open_profile(
        profile_mods_dir=_mods(tmp_path),
        game_root=tmp_path / "install",
        store_path=tmp_path / "Data" / "P.json",
        is_ee=True,
    )
    assert c.patch_ini_path == tmp_path / "install" / C.PATCH_INI_FILE
    _install_patch_hak(c, tmp_path)
    assert c.ctx.game_user_dir is not None
    assert not (c.ctx.game_user_dir / C.USER_PATCH_INI_FILE).exists()


def _mods(tmp_path: Path) -> Path:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return profile_mods
