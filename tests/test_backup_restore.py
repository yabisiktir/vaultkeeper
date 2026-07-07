"""Tests for Backup / Restore Data."""

from __future__ import annotations

import zipfile
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.pd.add_mod(ModData(group=C.GROUP_NONE, mod_name="Alpha"))
    controller.save()  # write the store JSON into Data/
    return controller


def test_backup_creates_zip(tmp_path):
    controller = _controller(tmp_path)
    dest = tmp_path / "backup.zip"
    message = controller.backup_data(dest)
    assert dest.is_file()
    assert "Backed up" in message
    with zipfile.ZipFile(dest) as z:
        assert "P.json" in z.namelist()


def test_restore_reloads_profile(tmp_path):
    controller = _controller(tmp_path)
    dest = tmp_path / "backup.zip"
    controller.backup_data(dest)

    # Mutate + persist a different state, then restore the backup.
    controller.remove_mods(["Alpha"])
    assert "Alpha" not in controller.pd.mod_list
    message = controller.restore_data(dest)
    assert "Restored" in message
    assert "Alpha" in controller.pd.mod_list
    # The engine points at the reloaded profile.
    assert controller.engine.pd is controller.pd


def test_backup_no_data(tmp_path):
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods, game_root=tmp_path / "NWN"
    )  # no store_path -> data_dir is the default; may or may not exist
    # With no store, data_dir() is the platform default; back up to a temp zip is fine
    # as long as it doesn't crash.
    controller.store_path = tmp_path / "Missing" / "P.json"
    assert "no data" in controller.backup_data(tmp_path / "b.zip").lower()
