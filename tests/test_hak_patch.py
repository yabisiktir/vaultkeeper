"""Tests for HakPatchManager (nwnpatch.ini regeneration)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.hak_patch import HakPatchManager
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State


def _install_hak(pd: ProfileData, name: str) -> None:
    ifk = FileKeyInfo.installed("patch", f"{name}.hak")
    pd.installed_list[ifk] = InstalledFileData(
        key=ifk, file_state=State.INSTALLED, extension=".hak"
    )


def test_empty_patch_ini(tmp_path: Path) -> None:
    pd = ProfileData()
    hpm = HakPatchManager(pd, tmp_path / C.PATCH_INI_FILE)
    hpm.create_nwn_patch_ini_file()
    text = (tmp_path / C.PATCH_INI_FILE).read_text()
    assert text == "[Patch]\nPatchFile000=\n"


def test_lists_installed_patch_haks(tmp_path: Path) -> None:
    pd = ProfileData()
    _install_hak(pd, "aaa")
    _install_hak(pd, "bbb")
    hpm = HakPatchManager(pd, tmp_path / C.PATCH_INI_FILE)
    hpm.create_nwn_patch_ini_file()
    lines = (tmp_path / C.PATCH_INI_FILE).read_text().splitlines()
    assert lines == ["[Patch]", "PatchFile000=aaa", "PatchFile001=bbb"]


def test_sequence_controls_order(tmp_path: Path) -> None:
    pd = ProfileData()
    _install_hak(pd, "aaa")
    _install_hak(pd, "bbb")
    _install_hak(pd, "ccc")  # not in sequence -> appended after ordered ones
    hpm = HakPatchManager(pd, tmp_path / C.PATCH_INI_FILE, sequence=["bbb", "aaa"])
    hpm.create_nwn_patch_ini_file()
    lines = (tmp_path / C.PATCH_INI_FILE).read_text().splitlines()
    assert lines == ["[Patch]", "PatchFile000=bbb", "PatchFile001=aaa", "PatchFile002=ccc"]


def test_backup_created_once(tmp_path: Path) -> None:
    ini = tmp_path / C.PATCH_INI_FILE
    ini.write_text("original content\n")
    pd = ProfileData()
    hpm = HakPatchManager(pd, ini)
    hpm.create_nwn_patch_ini_file()
    backup = tmp_path / (C.PATCH_INI_FILE + ".bak")
    assert backup.read_text() == "original content\n"  # preserved
    assert ini.read_text().startswith("[Patch]")
    # A second run does not overwrite the backup.
    _install_hak(pd, "later")
    hpm.create_nwn_patch_ini_file()
    assert backup.read_text() == "original content\n"


def test_updates_installed_record(tmp_path: Path) -> None:
    pd = ProfileData()
    ifk = FileKeyInfo.installed(C.MOD_ROOT_FOLDER, C.PATCH_INI_FILE)
    pd.installed_list[ifk] = InstalledFileData(key=ifk, extension=".ini", file_crc=0)
    hpm = HakPatchManager(pd, tmp_path / C.PATCH_INI_FILE)
    hpm.create_nwn_patch_ini_file()
    assert pd.installed_list[ifk].file_crc != 0  # CRC refreshed from the written file
    assert pd.installed_list[ifk].byte_size > 0
