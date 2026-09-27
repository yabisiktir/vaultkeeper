"""Mod identifiers follow what the mod is (VB ``ModData.ValidateInstallerType``).

NIT checks every mod with an installer on each profile load: a mod with source
files is an installer (``<mod>.nitins``), one without is a restorer
(``<mod>.nitres``). Vaultkeeper never did (logic audit stage 4), so a restorer
given source files stayed a restorer and Create Installer refused to build it,
and a mod could carry both identifiers.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _open(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _restorer(c: ProfileController, name: str) -> Path:
    c.create_mod(name)
    mod = c.ctx.profile_mods_dir / name
    payload = mod / C.MOD_INSTALLER_DIR / "override" / "a.2da"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"2DA")
    c.create_restorer(name)
    return mod


def test_a_restorer_given_source_files_becomes_an_installer(tmp_path: Path) -> None:
    c = _open(tmp_path)
    mod = _restorer(c, "Mixed")
    c.install(["Mixed"])
    (mod / "fresh.hak").write_bytes(b"HAK")  # e.g. Add Files

    c2 = _open(tmp_path)  # the next profile load

    md = c2.pd.mod_item("Mixed")
    assert md.is_installer() and not md.is_restorer()
    nit = mod / C.MOD_INSTALLER_DIR / C.MOD_NIT_DIR
    assert (nit / "Mixed.nitins").exists() and not (nit / "Mixed.nitres").exists()
    game_nit = c2.ctx.game_folders[C.MOD_NIT_DIR]
    assert (game_nit / "Mixed.nitins").exists() and not (game_nit / "Mixed.nitres").exists()
    assert c2.build_installer_payload("Mixed")["ok"]


def test_a_missing_identifier_is_created(tmp_path: Path) -> None:
    c = _open(tmp_path)
    c.create_mod("Bare")
    mod = c.ctx.profile_mods_dir / "Bare"
    (mod / C.MOD_INSTALLER_DIR / "hak").mkdir(parents=True)
    (mod / C.MOD_INSTALLER_DIR / "hak" / "x.hak").write_bytes(b"H")
    (mod / "x.hak").write_bytes(b"H")
    c.pd.scan_mod_files(c.pd.mod_item("Bare"), c.ctx.profile_mods_dir)
    assert not c.pd.mod_item("Bare").is_installer()

    assert c.validate_installer_types() == 1
    assert c.pd.mod_item("Bare").is_installer()


def test_a_correct_mod_is_left_alone(tmp_path: Path) -> None:
    c = _open(tmp_path)
    _restorer(c, "Clean")
    assert c.validate_installer_types() == 0
    assert c.pd.mod_item("Clean").is_restorer()


def test_marking_an_installer_drops_the_restorer_identifier(tmp_path: Path) -> None:
    c = _open(tmp_path)
    mod = _restorer(c, "Both")

    c.create_installer("Both")

    md = c.pd.mod_item("Both")
    assert md.is_installer() and not md.is_restorer()
    assert not (mod / C.MOD_INSTALLER_DIR / C.MOD_NIT_DIR / "Both.nitres").exists()
