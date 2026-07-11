"""Tests for keys-based install rescan (imported profiles → live-game state).

Covers ``ProfileData.rescan_installed_state`` and the ``open_profile`` auto-rescan
that lights up already-installed mods after a legacy import. See the method
docstring in ``core/profile_data.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController


def _mod(group: str, name: str, *filekeys: str) -> ModData:
    md = ModData(group=group, mod_name=name)
    md.files = [FileKeyInfo.mod_file(group, name, fk) for fk in filekeys]
    return md


def test_rescan_marks_present_mod_installed(tmp_path: Path) -> None:
    pd = ProfileData()
    pd.add_mod(_mod("G", "InGame", "hak\\a.hak"))
    pd.add_mod(_mod("G", "Missing", "hak\\b.hak"))
    pd.ensure_mandatory_groups()
    # Only a.hak is present in the game hak folder.
    hak = tmp_path / "game" / "hak"
    hak.mkdir(parents=True)
    (hak / "a.hak").write_bytes(b"data")
    folders = {"hak": hak}

    pd.rescan_installed_state(folders, root_folder_name="NWN")

    assert pd.mod_item("InGame").installed is True
    assert pd.mod_item("InGame").mod_state == State.INSTALLED
    assert pd.mod_item("Missing").installed is False
    assert pd.mod_item("Missing").mod_state == State.NOT_INSTALLED


def test_rescan_skips_group_items(tmp_path: Path) -> None:
    pd = ProfileData()
    pd.add_mod(_mod("G", "M", "hak\\a.hak"))
    pd.ensure_mandatory_groups()  # adds empty group items (mod_name == "")
    folders = {"hak": tmp_path / "hak"}
    (tmp_path / "hak").mkdir()
    (tmp_path / "hak" / "a.hak").write_bytes(b"x")
    # Must not raise on the group items (which have no real files).
    pd.rescan_installed_state(folders, root_folder_name="NWN")
    assert pd.mod_item("M").installed is True


def test_open_profile_auto_rescans_imported_profile(tmp_path: Path) -> None:
    """A loaded profile with mods but empty FileList rescans on open."""
    pd = ProfileData()
    pd.add_mod(_mod("G", "CEP", "hak\\cep.hak"))
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    assert not pd.file_list  # imported: no scanned FileList

    game_root = tmp_path / "NWN"
    user = tmp_path / "user"
    (user / "hak").mkdir(parents=True)
    (user / "hak" / "cep.hak").write_bytes(b"payload")

    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=game_root,
        store_path=store,
        game_user_dir=user,
        is_ee=True,
    )
    total, installed = controller.counts()
    assert (total, installed) == (1, 1)
    assert controller.pd.mod_item("CEP").installed is True


# --- Real-data golden (skipif absent) ------------------------------------- #
_NIT_STORE = Path("/Users/example/Documents/NIT Store")
_USER_DIR = Path("/Users/example/Documents/Neverwinter Nights")
_INSTALL = Path(
    "/Users/example/Library/Application Support/Steam/steamapps/common/Neverwinter Nights"
)


@pytest.mark.skipif(
    not (_NIT_STORE.is_dir() and _USER_DIR.is_dir() and _INSTALL.is_dir()),
    reason="No real NIT Store / NWN:EE install on this machine",
)
def test_real_import_open_shows_installed_grouped(tmp_path: Path) -> None:
    from vaultkeeper.persistence.nrbf.migrate import migrate_profile

    pd = migrate_profile(_NIT_STORE, "Enhanced Edition Mods")
    store = tmp_path / "Data" / "Enhanced Edition Mods.json"
    save_profile(pd, store)

    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=_INSTALL,
        store_path=store,
        game_user_dir=_USER_DIR,
        is_ee=True,
    )
    total, installed = controller.counts()
    assert total == 21
    assert installed == 2  # CEP + NIT Configuration Files (Auto)

    # Groups render with the owner's real custom groups.
    group_names = {
        g
        for g, members in controller.groups()
        if any(not m.is_group_item for m in members)
    }
    assert "100.  Community Packs" in group_names
    assert "799.  Mods Installed by NWN" in group_names
