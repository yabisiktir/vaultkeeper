"""Tests for the ProfileData in-memory engine: accessors, conflict resolution,
and the state pipeline."""

from __future__ import annotations

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import FileData, InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State

GROUP = "Group"
FILEKEY = "hak\\shared.hak"


def _installed_mod(pd: ProfileData, name: str, *, crc: int, installed: bool = True) -> FileKeyInfo:
    """Add a mod that installs FILEKEY with the given CRC; return its mod file key."""
    md = ModData(group=GROUP, mod_name=name)
    if installed:
        md.mod_state = State.INSTALLED
    fk = FileKeyInfo(GROUP, name, "hak", "shared.hak")
    md.files.append(fk)
    pd.add_mod(md)
    pd.add_file(FileData(key=fk, file_state=State.INSTALLED, file_crc=crc))
    return fk


def _installed_file(pd: ProfileData, crc: int) -> InstalledFileData:
    ifd = InstalledFileData(key=FileKeyInfo.installed("hak", "shared.hak"), file_crc=crc)
    pd.add_installed(ifd)
    return ifd


# --- accessors ------------------------------------------------------------ #
def test_accessors_and_keys() -> None:
    pd = ProfileData()
    pd.add_mod(ModData(group=GROUP, mod_name="Alpha"))
    pd.add_mod(ModData(group=GROUP))  # a group row
    assert pd.mod_exists("alpha")  # case-insensitive
    assert pd.mod_item("ALPHA") is not None
    assert pd.mod_keys == ["Alpha"]  # group row excluded


def test_group_keys_excludes_hidden() -> None:
    pd = ProfileData()
    pd.add_mod(ModData(group="Visible"))
    pd.add_mod(ModData(group=C.GROUP_INSTALLED))  # hidden
    assert pd.group_keys == ["Visible"]


# --- conflict-winner resolution (the core correctness path) --------------- #
def test_winner_is_greatest_mod_matching_crc() -> None:
    pd = ProfileData()
    fk_a = _installed_mod(pd, "Mod A", crc=100)
    fk_b = _installed_mod(pd, "Mod B", crc=100)
    ifd = _installed_file(pd, crc=100)

    pd.set_mod_files(ifd.key)

    # Both match CRC -> winner is the greatest by comparer (Mod B).
    assert ifd.installer == "Mod B"
    assert pd.file_list[fk_b].file_state == State.INSTALLED
    # The loser matches CRC -> MatchOverride, not Overridden.
    assert pd.file_list[fk_a].file_state == State.MATCH_OVERRIDE


def test_overridden_when_crc_differs() -> None:
    pd = ProfileData()
    fk_a = _installed_mod(pd, "Mod A", crc=100)
    fk_b = _installed_mod(pd, "Mod B", crc=200)
    ifd = _installed_file(pd, crc=200)  # matches Mod B

    pd.set_mod_files(ifd.key)

    assert ifd.installer == "Mod B"
    assert pd.file_list[fk_b].file_state == State.INSTALLED
    # Different CRC -> the other mod is truly overridden.
    assert pd.file_list[fk_a].file_state == State.OVERRIDDEN


def test_single_installer() -> None:
    pd = ProfileData()
    fk_a = _installed_mod(pd, "Only Mod", crc=42)
    ifd = _installed_file(pd, crc=42)
    pd.set_mod_files(ifd.key)
    assert ifd.installer == "Only Mod"
    assert pd.file_list[fk_a].file_state == State.INSTALLED


def test_numeric_mod_names_pick_correct_winner() -> None:
    pd = ProfileData()
    _installed_mod(pd, "Mod 2", crc=1)
    _installed_mod(pd, "Mod 10", crc=1)
    ifd = _installed_file(pd, crc=1)
    pd.set_mod_files(ifd.key)
    # Natural sort: "Mod 10" > "Mod 2" -> it wins.
    assert ifd.installer == "Mod 10"


# --- default installer (no mod owns the file = original game file) -------- #
def test_default_installer_original() -> None:
    pd = ProfileData()
    pd.original_files["hak\\core.hak"] = 555
    ifd = InstalledFileData(key=FileKeyInfo.installed("hak", "core.hak"), file_crc=555)
    pd.add_installed(ifd)
    pd.set_mod_files(ifd.key)  # no mod files -> default classification
    assert ifd.installer == C.INSTALLER_ORIGINAL


def test_default_installer_character() -> None:
    pd = ProfileData()
    ifd = InstalledFileData(
        key=FileKeyInfo.installed("localvault", "hero.bic"), extension=".bic", file_crc=7
    )
    pd.add_installed(ifd)
    pd.set_mod_files(ifd.key)
    assert ifd.installer == C.INSTALLER_CHARACTER


def test_default_installer_unknown() -> None:
    pd = ProfileData()
    ifd = InstalledFileData(key=FileKeyInfo.installed("hak", "mystery.hak"), file_crc=9)
    pd.add_installed(ifd)
    pd.set_mod_files(ifd.key)
    assert ifd.installer == C.INSTALLER_UNKNOWN


# --- remove_mod_file re-resolves the winner ------------------------------- #
def test_remove_winning_mod_file_reassigns() -> None:
    pd = ProfileData()
    _installed_mod(pd, "Mod A", crc=100)
    fk_b = _installed_mod(pd, "Mod B", crc=100)
    ifd = _installed_file(pd, crc=100)
    pd.set_mod_files(ifd.key)
    assert ifd.installer == "Mod B"

    # Remove the winning mod's file -> installer falls back to Mod A.
    pd.remove_mod_file(ifd, fk_b, conflicts=True)
    assert ifd.installer == "Mod A"
    assert fk_b not in ifd.mod_files


# --- state pipeline ------------------------------------------------------- #
def test_update_mod_states_uses_affected() -> None:
    pd = ProfileData()
    md = ModData(group=GROUP, mod_name="Mod A")
    fk = FileKeyInfo(GROUP, "Mod A", "hak", "a.hak")
    md.files.append(fk)
    pd.add_mod(md)
    pd.add_file(FileData(key=fk, file_state=State.INSTALLED, file_crc=1))
    pd.changes.mods.affected("Mod A")
    pd.update_mod_states()
    assert md.mod_state == State.INSTALLED


def test_update_file_states_resolves_installed_updates() -> None:
    pd = ProfileData()
    _installed_mod(pd, "Mod A", crc=5)
    ifd = _installed_file(pd, crc=5)
    # Queue the installed file for an update and run the pipeline.
    pd.changes.installed.added(ifd.key)
    pd.update_file_states()
    assert ifd.installer == "Mod A"
    assert pd.changes.installed.update_list == []
