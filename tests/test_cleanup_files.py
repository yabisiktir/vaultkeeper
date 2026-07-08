"""Tests for the per-mod file-removal cleanups (ERF / Leto log)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller_with_mod(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    installer = profile_mods / "My Mod" / C.MOD_INSTALLER_DIR
    (installer / "hak").mkdir(parents=True)
    (installer / "hak" / "content.hak").write_bytes(b"HAK")
    (installer / "erf").mkdir()
    (installer / "erf" / "extra.erf").write_bytes(b"ERF")
    (installer / "override").mkdir()
    (installer / "override" / C.LETO_LOG_FILENAME).write_bytes(b"log")
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.create_installer("My Mod")  # registers all payload files
    return controller


def test_remove_erf_files(tmp_path):
    controller = _controller_with_mod(tmp_path)
    installer = tmp_path / "Profiles" / "P" / "My Mod" / C.MOD_INSTALLER_DIR
    assert (installer / "erf" / "extra.erf").exists()

    removed = controller.remove_erf_files("My Mod")
    assert removed == 1
    assert not (installer / "erf" / "extra.erf").exists()
    # The hak payload is untouched.
    assert (installer / "hak" / "content.hak").exists()
    md = controller.pd.mod_item("My Mod")
    assert not any(fk.filename.endswith(".erf") for fk in md.files)


def test_remove_leto_log_files(tmp_path):
    controller = _controller_with_mod(tmp_path)
    installer = tmp_path / "Profiles" / "P" / "My Mod" / C.MOD_INSTALLER_DIR
    removed = controller.remove_leto_log_files("My Mod")
    assert removed == 1
    assert not (installer / "override" / C.LETO_LOG_FILENAME).exists()


def test_remove_on_unknown_mod(tmp_path):
    controller = _controller_with_mod(tmp_path)
    assert controller.remove_erf_files("Ghost") == 0
