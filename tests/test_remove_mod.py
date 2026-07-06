"""Tests for ProfileData.remove_mod (removing a mod definition)."""

from __future__ import annotations

from vaultkeeper.core.file_data import FileData, InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State

GROUP = "G"


def _add_mod_with_file(pd: ProfileData, name: str, folder: str, filename: str, crc: int):
    md = ModData(group=GROUP, mod_name=name)
    md.mod_state = State.INSTALLED
    fk = FileKeyInfo(GROUP, name, folder, filename)
    md.files.append(fk)
    pd.add_mod(md)
    pd.add_file(FileData(key=fk, file_state=State.INSTALLED, file_crc=crc))
    return fk


def test_remove_mod_deletes_from_lists() -> None:
    pd = ProfileData()
    fk = _add_mod_with_file(pd, "Solo", "hak", "s.hak", 1)
    ifk = FileKeyInfo.installed("hak", "s.hak")
    pd.installed_list[ifk] = InstalledFileData(key=ifk, file_crc=1, installer="Solo")
    pd.set_mod_files(ifk)

    assert pd.remove_mod("Solo")
    assert "Solo" not in pd.mod_keys
    assert fk not in pd.file_list


def test_remove_mod_reassigns_shared_file() -> None:
    pd = ProfileData()
    _add_mod_with_file(pd, "Mod A", "override", "x.2da", 5)
    _add_mod_with_file(pd, "Mod B", "override", "x.2da", 5)
    ifk = FileKeyInfo.installed("override", "x.2da")
    pd.installed_list[ifk] = InstalledFileData(key=ifk, file_crc=5)
    pd.set_mod_files(ifk)
    assert pd.installed_list[ifk].installer == "Mod B"  # greater wins

    # Removing the current owner reassigns the installed file to Mod A.
    assert pd.remove_mod("Mod B")
    assert "Mod B" not in pd.mod_keys
    assert pd.installed_list[ifk].installer == "Mod A"


def test_remove_unknown_mod_is_noop() -> None:
    pd = ProfileData()
    assert not pd.remove_mod("Ghost")


def test_remove_group_row_ignored() -> None:
    pd = ProfileData()
    pd.add_mod(ModData(group="MyGroup"))  # group row
    assert not pd.remove_mod("MyGroup")
    assert "MyGroup" in (md.group for md in pd.mod_list.values())
