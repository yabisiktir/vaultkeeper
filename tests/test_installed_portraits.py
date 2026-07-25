"""Tests for installed-portrait report + removal (VB PortraitManager PopulatePortraits/Exclude)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController

_SIZES = ("t", "s", "m", "l", "h")


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _install_portrait(controller: ProfileController, tmp_path: Path, mod: str, resref: str) -> None:
    controller.create_mod(mod)
    installer = tmp_path / "Profiles" / "P" / mod / C.MOD_INSTALLER_DIR / "portraits"
    installer.mkdir(parents=True, exist_ok=True)
    for size in _SIZES:
        (installer / f"{resref}{size}.tga").write_bytes(b"TGA" + size.encode())
    controller.build_installer_payload(mod)
    controller.install([mod])


def test_installed_portraits_report_groups_by_mod(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _install_portrait(c, tmp_path, "Heroes Pack", "po_hero")
    _install_portrait(c, tmp_path, "Royal Set", "po_king")

    report = c.installed_portraits_report()
    by_resref = {p["resref"]: p for p in report["portraits"]}
    assert set(by_resref) == {"po_hero", "po_king"}
    assert by_resref["po_hero"]["mod"] == "Heroes Pack"
    assert by_resref["po_king"]["mod"] == "Royal Set"
    # All five sizes are collected as game paths.
    assert set(by_resref["po_hero"]["sizes"]) == set(_SIZES)


def test_remove_installed_portrait_deletes_from_game_and_installer(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    _install_portrait(c, tmp_path, "Heroes Pack", "po_hero")
    game_portraits = c.ctx.game_folders["portraits"]
    assert (game_portraits / "po_heroh.tga").is_file()

    result = c.remove_installed_portrait("po_hero")
    assert result["removed"] == 5
    assert result["mod"] == "Heroes Pack"
    # Gone from the game folder…
    assert not (game_portraits / "po_heroh.tga").exists()
    # …and no longer reported.
    assert c.installed_portraits_report()["count"] == 0
    # …and dropped from the mod's installer so it won't reinstall.
    installer = tmp_path / "Profiles" / "P" / "Heroes Pack" / C.MOD_INSTALLER_DIR / "portraits"
    assert not (installer / "po_heroh.tga").exists()


def test_non_portrait_files_ignored(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    # A portrait mod + a hak mod; only the portrait should surface.
    _install_portrait(c, tmp_path, "Heroes Pack", "po_hero")
    c.create_mod("Hak Mod")
    hak_dir = tmp_path / "Profiles" / "P" / "Hak Mod" / C.MOD_INSTALLER_DIR / "hak"
    hak_dir.mkdir(parents=True)
    (hak_dir / "stuff.hak").write_bytes(b"HAK")
    c.build_installer_payload("Hak Mod")
    c.install(["Hak Mod"])

    report = c.installed_portraits_report()
    assert {p["resref"] for p in report["portraits"]} == {"po_hero"}
