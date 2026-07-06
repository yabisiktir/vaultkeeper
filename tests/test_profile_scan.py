"""Tests for ProfileData disk scanning and checksum calculation."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.crc import crc32_bytes
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State


def _make_mod(profile_mods: Path, name: str, files: dict[str, bytes]) -> None:
    """Create a mod folder with an installer payload: {"hak/x.hak": data, ...}."""
    installer = profile_mods / name / C.MOD_INSTALLER_DIR
    for rel, data in files.items():
        target = installer / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def test_scan_mods_discovers_mods_and_files(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "My Mods"
    _make_mod(profile_mods, "Alpha", {"hak/a.hak": b"aaa", "modules/w.mod": b"m"})
    _make_mod(profile_mods, "Beta", {"override/o.tga": b"tga"})

    pd = ProfileData()
    pd.scan_mods(profile_mods)

    assert set(pd.mod_keys) == {"Alpha", "Beta"}
    # Alpha has 2 files with correct keys/folders.
    alpha = pd.mod_item("Alpha")
    assert alpha is not None
    folders = {fk.folder for fk in alpha.files}
    assert folders == {"hak", "modules"}
    assert all(fk.group == C.GROUP_NONE for fk in alpha.files)
    # FileList populated; states Unknown, crc 0 until calculated.
    fk = next(f for f in alpha.files if f.filename == "a.hak")
    assert pd.file_list[fk].file_state == State.UNKNOWN
    assert pd.file_list[fk].byte_size == 3


def test_scan_skips_reserved_and_loose_files(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(profile_mods, "Alpha", {"hak/a.hak": b"x"})
    # A file loose in the installer root (not in a subfolder) is ignored.
    (profile_mods / "Alpha" / C.MOD_INSTALLER_DIR / "loose.txt").write_bytes(b"y")
    # A reserved folder name is not treated as a mod.
    (profile_mods / C.DOWNLOADS_DIR).mkdir(parents=True)

    pd = ProfileData()
    pd.scan_mods(profile_mods)

    assert pd.mod_keys == ["Alpha"]
    alpha = pd.mod_item("Alpha")
    assert alpha is not None
    assert [fk.filename for fk in alpha.files] == ["a.hak"]  # loose.txt excluded


def test_scan_installed_and_root_normalisation(tmp_path: Path) -> None:
    game_root = tmp_path / "Neverwinter Nights"
    (game_root / "hak").mkdir(parents=True)
    (game_root / "hak" / "core.hak").write_bytes(b"h")
    (game_root / "nwn.ini").write_bytes(b"i")  # a root-level file

    mapper = Mapper(is_ee=True)
    folders = mapper.nwn_folder_paths(game_root)

    pd = ProfileData()
    pd.scan_installed(folders, root_folder_name=game_root.name)

    from vaultkeeper.core.file_key import FileKeyInfo

    assert FileKeyInfo.installed("hak", "core.hak") in pd.installed_list
    # The root-level file normalises its folder to the "nwn" marker.
    assert FileKeyInfo.installed("nwn", "nwn.ini") in pd.installed_list


def test_calculate_checksums(tmp_path: Path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(profile_mods, "Alpha", {"hak/a.hak": b"hello"})
    pd = ProfileData()
    pd.scan_mods(profile_mods)

    # Before: crc 0.
    fk = pd.mod_item("Alpha").files[0]
    assert pd.file_list[fk].file_crc == 0

    pd.calculate_checksums(profile_mods, game_folders={})
    assert pd.file_list[fk].file_crc == crc32_bytes(b"hello")


def test_full_scan_then_resolve_conflict(tmp_path: Path) -> None:
    # Two mods ship the same override file; after scan+checksum+state pipeline,
    # the greater mod owns the installed copy.
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(profile_mods, "Mod A", {"override/shared.2da": b"same"})
    _make_mod(profile_mods, "Mod B", {"override/shared.2da": b"same"})

    game_root = tmp_path / "NWN"
    (game_root / "override").mkdir(parents=True)
    (game_root / "override" / "shared.2da").write_bytes(b"same")

    mapper = Mapper(is_ee=True)
    folders = mapper.nwn_folder_paths(game_root)

    pd = ProfileData()
    pd.scan_mods(profile_mods)
    pd.scan_installed(folders, root_folder_name=game_root.name)
    pd.calculate_checksums(profile_mods, folders)
    # Mark both mods installed so the owner-resolution loop can pick a winner.
    for name in ("Mod A", "Mod B"):
        pd.mod_item(name).mod_state = State.INSTALLED
    pd.update_file_states()

    from vaultkeeper.core.file_key import FileKeyInfo

    ifd = pd.installed_list[FileKeyInfo.installed("override", "shared.2da")]
    assert ifd.installer == "Mod B"  # greatest by comparer wins
