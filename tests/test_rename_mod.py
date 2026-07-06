"""Tests for ProfileData.rename_mod (folder + file-key + identifier rename)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.core.profile_data import ProfileData


def _make_mod(profile_mods: Path, name: str, files: dict[str, bytes]) -> None:
    installer = profile_mods / name / C.MOD_INSTALLER_DIR
    for rel, data in files.items():
        target = installer / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _loaded(profile_mods: Path) -> ProfileData:
    pd = ProfileData()
    pd.scan_mods(profile_mods)
    pd.update_file_states()
    pd.update_mod_states()
    pd.changes.reset_changes()
    return pd


def test_rename_moves_folder_and_rewrites_keys(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(profile_mods, "Old Name", {"hak/a.hak": b"AAA", "override/b.2da": b"BBB"})
    pd = _loaded(profile_mods)

    assert pd.rename_mod("Old Name", "New Name", profile_mods)

    # Folder renamed on disk.
    assert not (profile_mods / "Old Name").exists()
    assert (profile_mods / "New Name" / C.MOD_INSTALLER_DIR / "hak" / "a.hak").is_file()
    # ModList + file keys updated.
    assert "New Name" in pd.mod_keys
    assert "Old Name" not in pd.mod_keys
    md = pd.mod_item("New Name")
    assert md is not None
    assert all(fk.mod_name == "New Name" for fk in md.files)
    assert all(fk in pd.file_list for fk in md.files)


def test_rename_renames_identifier_file(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(
        profile_mods,
        "Adventure",
        {"hak/a.hak": b"AAA", f"{C.MOD_NIT_DIR}/Adventure.nitins": b""},
    )
    pd = _loaded(profile_mods)
    assert pd.rename_mod("Adventure", "Epic Quest", profile_mods)

    nit = profile_mods / "Epic Quest" / C.MOD_INSTALLER_DIR / C.MOD_NIT_DIR
    assert (nit / "Epic Quest.nitins").is_file()
    assert not (nit / "Adventure.nitins").exists()
    md = pd.mod_item("Epic Quest")
    assert any(fk.filename == "Epic Quest.nitins" for fk in md.files)


def test_rename_installed_identifier_in_game(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    game_root = tmp_path / "NWN"
    _make_mod(profile_mods, "Adventure", {f"{C.MOD_NIT_DIR}/Adventure.nitins": b""})
    pd = _loaded(profile_mods)
    mapper = Mapper(is_ee=True)
    game_folders = mapper.nwn_folder_paths(game_root)
    # Simulate the identifier being installed in the game.
    from vaultkeeper.core.file_data import InstalledFileData
    from vaultkeeper.core.file_key import FileKeyInfo

    ik = FileKeyInfo.installed(C.MOD_NIT_DIR, "Adventure.nitins")
    pd.installed_list[ik] = InstalledFileData(key=ik, extension=".nitins")
    game_nit = game_folders[C.MOD_NIT_DIR]
    game_nit.mkdir(parents=True, exist_ok=True)
    (game_nit / "Adventure.nitins").write_bytes(b"")

    assert pd.rename_mod("Adventure", "Quest", profile_mods, game_folders)
    assert (game_nit / "Quest.nitins").is_file()
    assert not (game_nit / "Adventure.nitins").exists()
    assert FileKeyInfo.installed(C.MOD_NIT_DIR, "Quest.nitins") in pd.installed_list


def test_rename_rejects_existing_target(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(profile_mods, "A", {"hak/a.hak": b"a"})
    _make_mod(profile_mods, "B", {"hak/b.hak": b"b"})
    pd = _loaded(profile_mods)
    assert not pd.rename_mod("A", "B", profile_mods)  # target exists
    assert not pd.rename_mod("Ghost", "C", profile_mods)  # source missing
