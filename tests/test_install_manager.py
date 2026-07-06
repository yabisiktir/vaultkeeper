"""Golden tests for the install/uninstall/anneal engine against a real profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.install_manager import InstallContext, IOResult, ModInstallationManager
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State


def _make_mod(profile_mods: Path, name: str, files: dict[str, bytes]) -> None:
    installer = profile_mods / name / C.MOD_INSTALLER_DIR
    for rel, data in files.items():
        target = installer / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


@pytest.fixture()
def setup(tmp_path: Path):
    profile_mods = tmp_path / "Profiles" / "P"
    game_root = tmp_path / "NWN"
    # Two mods sharing an override file (same content) plus a unique hak each.
    _make_mod(profile_mods, "Mod A", {"override/shared.2da": b"data", "hak/a.hak": b"AAA"})
    _make_mod(profile_mods, "Mod B", {"override/shared.2da": b"data", "hak/b.hak": b"BBB"})

    mapper = Mapper(is_ee=True)
    game_folders = mapper.nwn_folder_paths(game_root)

    pd = ProfileData()
    pd.scan_mods(profile_mods)
    pd.scan_installed(game_folders, root_folder_name=game_root.name)
    pd.calculate_checksums(profile_mods, game_folders)
    # Establish initial file/mod states from the scan (the real load sequence);
    # without this, un-held mod files stay Unknown and SetModState misbehaves.
    pd.update_file_states()
    pd.update_mod_states()
    pd.changes.reset_changes()

    ctx = InstallContext(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        game_folders=game_folders,
        root_folder_name=game_root.name,
        mapper=mapper,
        is_ee=True,
    )
    mgr = ModInstallationManager(pd, ctx)
    return pd, ctx, mgr, game_root


def _install(mgr: ModInstallationManager, pd: ProfileData, name: str) -> None:
    keys = list(pd.mod_item(name).files)
    mgr.install_files(keys, anneal_mods=[name])


def test_install_single_mod_copies_files(setup) -> None:
    pd, ctx, mgr, game_root = setup
    _install(mgr, pd, "Mod A")

    # Physical files present in the game folder.
    assert (game_root / "override" / "shared.2da").is_file()
    assert (game_root / "hak" / "a.hak").is_file()
    # Installed list + ownership + mod state.
    ifk = FileKeyInfo.installed("override", "shared.2da")
    assert ifk in pd.installed_list
    assert pd.installed_list[ifk].installer == "Mod A"
    assert pd.mod_item("Mod A").mod_state == State.INSTALLED
    assert mgr.result in (IOResult.SUCCESS, IOResult.NO_SOURCE_ITEMS)


def test_second_mod_wins_shared_file(setup) -> None:
    pd, ctx, mgr, game_root = setup
    _install(mgr, pd, "Mod A")
    _install(mgr, pd, "Mod B")

    ifk = FileKeyInfo.installed("override", "shared.2da")
    # Mod B is the greater name -> it wins ownership of the shared file.
    assert pd.installed_list[ifk].installer == "Mod B"
    # Both unique haks are installed.
    assert (game_root / "hak" / "a.hak").is_file()
    assert (game_root / "hak" / "b.hak").is_file()
    # Mod A's shared file becomes a match-override (same CRC, not the winner).
    fk_a_shared = FileKeyInfo(C.GROUP_NONE, "Mod A", "override", "shared.2da")
    assert pd.file_list[fk_a_shared].file_state == State.MATCH_OVERRIDE


def test_uninstall_reassigns_and_deletes(setup) -> None:
    pd, ctx, mgr, game_root = setup
    _install(mgr, pd, "Mod A")
    _install(mgr, pd, "Mod B")

    # Uninstall Mod B: its unique hak goes; the shared file reverts to Mod A.
    mgr.uninstall_files(list(pd.mod_item("Mod B").files), anneal_mods=["Mod A"])

    assert not (game_root / "hak" / "b.hak").exists()
    ifk = FileKeyInfo.installed("override", "shared.2da")
    assert ifk in pd.installed_list  # still installed (owned by Mod A now)
    assert pd.installed_list[ifk].installer == "Mod A"
    assert (game_root / "hak" / "a.hak").is_file()


def test_uninstall_only_mod_removes_all(setup) -> None:
    pd, ctx, mgr, game_root = setup
    _install(mgr, pd, "Mod A")
    mgr.uninstall_files(list(pd.mod_item("Mod A").files), anneal_mods=[])

    assert not (game_root / "override" / "shared.2da").exists()
    assert not (game_root / "hak" / "a.hak").exists()
    assert FileKeyInfo.installed("override", "shared.2da") not in pd.installed_list
    assert pd.mod_item("Mod A").mod_state == State.NOT_INSTALLED


def test_no_copies_when_nothing_to_do(tmp_path: Path) -> None:
    # A mod with a single LARGE file (>5121 bytes): once installed with a matching
    # CRC, re-installing needs no copy (the small-file guard doesn't apply).
    profile_mods = tmp_path / "Profiles" / "P"
    game_root = tmp_path / "NWN"
    _make_mod(profile_mods, "Big Mod", {"hak/big.hak": b"Z" * 6000})

    mapper = Mapper(is_ee=True)
    game_folders = mapper.nwn_folder_paths(game_root)
    pd = ProfileData()
    pd.scan_mods(profile_mods)
    pd.scan_installed(game_folders, root_folder_name=game_root.name)
    pd.calculate_checksums(profile_mods, game_folders)
    pd.update_file_states()
    pd.update_mod_states()
    pd.changes.reset_changes()

    ctx = InstallContext(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        game_folders=game_folders,
        root_folder_name=game_root.name,
        mapper=mapper,
        is_ee=True,
    )
    mgr = ModInstallationManager(pd, ctx)
    keys = list(pd.mod_item("Big Mod").files)
    mgr.install_files(keys, anneal_mods=["Big Mod"])
    # Re-installing: file present with matching CRC and >= 5121 bytes -> no copy.
    mgr.install_files(keys, anneal_mods=["Big Mod"])
    assert mgr.result == IOResult.NO_SOURCE_ITEMS
    assert mgr.result_message == "No file copies required."


def test_small_file_always_copied(setup) -> None:
    # The shared.2da is 4 bytes (< 5121), so a re-install re-copies it even though
    # the CRC matches — exercising the collision guard (no NO_SOURCE_ITEMS here).
    pd, ctx, mgr, game_root = setup
    _install(mgr, pd, "Mod A")
    target = game_root / "override" / "shared.2da"
    target.write_bytes(b"XXXX")  # tamper with the installed copy
    mgr.install_files(
        [FileKeyInfo(C.GROUP_NONE, "Mod A", "override", "shared.2da")], anneal_mods=["Mod A"]
    )
    # It was copied again (guard forces copy for tiny files), restoring content.
    assert target.read_bytes() == b"data"
