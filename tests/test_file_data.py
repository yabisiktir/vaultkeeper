"""Tests for State/Ratings enums and FileData/InstalledFileData records."""

from __future__ import annotations

from datetime import datetime

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import FileData, InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.state import Ratings, State


# --- enums: data-contract integer values ---------------------------------- #
def test_state_values() -> None:
    assert State.NONE == -2
    assert State.NOT_INSTALLED == 1
    assert State.SOME_INSTALLED == 2
    assert State.SOME_AND_OVERRIDDEN == 4
    assert State.INSTALL_STATE == 10
    assert State.INSTALLED == 11
    assert State.MATCH_OVERRIDE == 12
    assert State.OVERRIDDEN == 14


def test_state_thresholds() -> None:
    assert not State.NOT_INSTALLED.is_file_installed
    assert State.INSTALLED.is_file_installed
    assert State.OVERRIDDEN.is_file_installed
    assert not State.SOME_INSTALLED.is_mod_installed  # partial < InstallState
    assert State.INSTALLED.is_mod_installed


def test_ratings_values() -> None:
    assert Ratings.NONE == 0
    assert Ratings.EXCELLENT == 1
    assert Ratings.MEDIUM == 3
    assert Ratings.ABANDONED == 7


# --- FileData ------------------------------------------------------------- #
def _key() -> FileKeyInfo:
    return FileKeyInfo("G", "Mod", "hak", "a.hak")


def test_filedata_installed_property() -> None:
    fd = FileData(key=_key(), file_state=State.NOT_INSTALLED)
    assert not fd.installed
    fd.file_state = State.INSTALLED
    assert fd.installed


def test_crc_calculated() -> None:
    assert not FileData(key=_key(), file_crc=0, byte_size=10).crc_calculated
    assert FileData(key=_key(), file_crc=123, byte_size=10).crc_calculated
    assert FileData(key=_key(), file_crc=0, byte_size=0).crc_calculated  # empty file


def test_filedata_clone() -> None:
    fd = FileData(
        key=_key(),
        file_state=State.INSTALLED,
        extension=".hak",
        modified=datetime(2020, 1, 1),
        byte_size=42,
        file_crc=99,
    )
    c = fd.clone()
    assert c is not fd
    assert (c.file_state, c.extension, c.byte_size, c.file_crc) == (
        State.INSTALLED,
        ".hak",
        42,
        99,
    )


# --- InstalledFileData ---------------------------------------------------- #
def test_installed_defaults() -> None:
    ifd = InstalledFileData(key=FileKeyInfo.installed("hak", "a.hak"))
    assert ifd.installer == C.INSTALLER_UNKNOWN
    assert ifd.mod_files == []
    assert ifd.mod_file_conflicts == []
    assert ifd.is_unknown_installer


def test_default_installer_detection() -> None:
    ifd = InstalledFileData(key=FileKeyInfo.installed("hak", "a.hak"))
    ifd.installer = C.INSTALLER_ORIGINAL
    assert ifd.is_default_installer
    ifd.installer = "Some User Mod"
    assert not ifd.is_default_installer
    assert not ifd.is_unknown_installer


def test_unknown_installer_includes_character() -> None:
    ifd = InstalledFileData(key=FileKeyInfo.installed("d", "c.bic"))
    ifd.installer = C.INSTALLER_CHARACTER
    assert ifd.is_unknown_installer


def test_installed_clone_copies_mod_files_not_key() -> None:
    ifd = InstalledFileData(
        key=FileKeyInfo.installed("hak", "a.hak"),
        installer="Mod X",
        file_crc=5,
    )
    ifd.mod_files.append(FileKeyInfo("G", "Mod X", "hak", "a.hak"))
    c = ifd.clone()
    assert c.installer == "Mod X"
    assert c.file_crc == 5
    assert len(c.mod_files) == 1
    # Independent list copy.
    c.mod_files.clear()
    assert len(ifd.mod_files) == 1
