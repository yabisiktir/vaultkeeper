"""Tests for Add Files to Mod."""

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
    controller.create_mod("My Mod")
    return controller


def test_add_files_maps_to_folders(tmp_path):
    controller = _controller(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    hak = src / "content.hak"
    twoda = src / "rules.2da"
    hak.write_bytes(b"HAK")
    twoda.write_bytes(b"2DA")

    added = controller.add_files_to_mod("My Mod", [hak, twoda])
    assert added == 2

    installer = tmp_path / "Profiles" / "P" / "My Mod" / C.MOD_INSTALLER_DIR
    hak_folder = controller.ctx.mapper.get_mapped_folder("content.hak")
    twoda_folder = controller.ctx.mapper.get_mapped_folder("rules.2da")
    assert (installer / hak_folder / "content.hak").is_file()
    assert (installer / twoda_folder / "rules.2da").is_file()

    # Both files are now tracked on the mod.
    md = controller.pd.mod_item("My Mod")
    filenames = {fk.filename for fk in md.files}
    assert {"content.hak", "rules.2da"} <= filenames


def test_add_files_ignores_missing(tmp_path):
    controller = _controller(tmp_path)
    assert controller.add_files_to_mod("My Mod", [tmp_path / "nope.hak"]) == 0


def test_add_files_unknown_mod(tmp_path):
    controller = _controller(tmp_path)
    src = tmp_path / "a.hak"
    src.write_bytes(b"x")
    assert controller.add_files_to_mod("Ghost", [src]) == 0
