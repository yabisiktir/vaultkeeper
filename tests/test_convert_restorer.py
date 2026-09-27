"""Tests for Convert Restorer -> Mod (VB NIT.Menu.vb MsConvertRestorer_Click)."""

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


def _restorer_with_payload(controller: ProfileController, tmp_path: Path, name: str):
    controller.create_mod(name)
    payload = (
        tmp_path / "Profiles" / "P" / name / C.MOD_INSTALLER_DIR / "override" / "a.tga"
    )
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"TGADATA")
    controller.create_restorer(name)
    return controller.pd.mod_item(name)


def test_convert_restorer_swaps_identifier(tmp_path):
    controller = _controller(tmp_path)
    md = _restorer_with_payload(controller, tmp_path, "Base Restorer")
    assert md.is_restorer() and not md.is_installer()

    assert controller.convert_restorer("Base Restorer") == 1

    md = controller.pd.mod_item("Base Restorer")
    assert md.is_installer()
    assert not md.is_restorer()
    nit_dir = (
        tmp_path / "Profiles" / "P" / "Base Restorer" / C.MOD_INSTALLER_DIR / C.MOD_NIT_DIR
    )
    assert (nit_dir / f"Base Restorer{C.EXT_INSTALLER}").is_file()
    assert not (nit_dir / f"Base Restorer{C.EXT_RESTORER}").exists()
    # The payload file survives the conversion (only the identifier changed).
    assert any(fk.filename == "a.tga" for fk in md.files)


def test_convert_restorer_no_payload_returns_zero(tmp_path):
    controller = _controller(tmp_path)
    # A restorer whose only file is the .nitres identifier -> nothing to convert.
    controller.create_mod("Empty Restorer")
    controller.create_restorer("Empty Restorer")
    md = controller.pd.mod_item("Empty Restorer")
    assert md.is_restorer()

    assert controller.convert_restorer("Empty Restorer") == 0
    # Still a restorer (unchanged).
    assert controller.pd.mod_item("Empty Restorer").is_restorer()


def test_convert_restorer_rejects_non_restorer(tmp_path):
    controller = _controller(tmp_path)
    controller.create_mod("Just A Mod")
    controller.create_installer("Just A Mod")
    assert controller.convert_restorer("Just A Mod") == -1


def test_convert_restorer_unknown_mod(tmp_path):
    controller = _controller(tmp_path)
    assert controller.convert_restorer("Nope") == -1


def test_the_payload_becomes_the_mods_source(tmp_path):
    """VB moves the restorer's folders to _Downloads and runs Create Installer."""
    controller = _controller(tmp_path)
    _restorer_with_payload(controller, tmp_path, "Base Restorer")
    mod = tmp_path / "Profiles" / "P" / "Base Restorer"

    assert controller.convert_restorer("Base Restorer") == 1

    assert (mod / C.DOWNLOADS_DIR / "override" / "a.tga").read_bytes() == b"TGADATA"
    assert (mod / C.MOD_INSTALLER_DIR / "override" / "a.tga").read_bytes() == b"TGADATA"


def test_a_converted_restorer_keeps_its_payload_through_a_rebuild(tmp_path):
    """Before: the payload lived only in the installer, so adding a file and
    rebuilding recycled it and built the mod from the new file alone."""
    controller = _controller(tmp_path)
    _restorer_with_payload(controller, tmp_path, "Base Restorer")
    controller.convert_restorer("Base Restorer")
    extra = tmp_path / "extra.hak"
    extra.write_bytes(b"HAK")

    controller.add_files_to_mod("Base Restorer", [extra])
    assert controller.build_installer_payload("Base Restorer")["ok"]

    files = {fk.filename for fk in controller.pd.mod_item("Base Restorer").files}
    assert {"a.tga", "extra.hak"} <= files


def test_an_installed_restorer_is_installed_again(tmp_path):
    controller = _controller(tmp_path)
    _restorer_with_payload(controller, tmp_path, "Base Restorer")
    controller.install(["Base Restorer"])
    assert controller._mod_installed("Base Restorer")

    controller.convert_restorer("Base Restorer")

    assert controller._mod_installed("Base Restorer")
    assert controller.pd.mod_item("Base Restorer").is_installer()
