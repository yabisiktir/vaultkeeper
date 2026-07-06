"""Tests for ProfileData installation-analysis accessors."""

from __future__ import annotations

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.core.profile_data import ProfileData


def _installed(pd: ProfileData, folder: str, name: str, *, installer: str, crc: int) -> FileKeyInfo:
    fk = FileKeyInfo.installed(folder, name)
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    pd.installed_list[fk] = InstalledFileData(
        key=fk, extension=ext, installer=installer, file_crc=crc
    )
    return fk


def test_unknown_source_files() -> None:
    pd = ProfileData()
    mapper = Mapper(is_ee=True)
    _installed(pd, "hak", "mystery.hak", installer=C.INSTALLER_UNKNOWN, crc=1)
    _installed(pd, "hak", "owned.hak", installer="Some Mod", crc=2)
    _installed(pd, "hak", "weird.xyz", installer=C.INSTALLER_UNKNOWN, crc=3)  # unmapped ext
    unknown = pd.unknown_source_files(mapper)
    names = {fk.filename for fk in unknown}
    assert names == {"mystery.hak"}  # owned excluded; unmapped-ext excluded


def test_original_and_changed_files() -> None:
    pd = ProfileData()
    pd.original_files["hak\\core.hak"] = 100
    pd.original_files["data\\base.bif"] = 200
    _installed(pd, "hak", "core.hak", installer=C.INSTALLER_ORIGINAL, crc=100)   # pristine
    _installed(pd, "data", "base.bif", installer=C.INSTALLER_ORIGINAL, crc=999)  # changed
    _installed(pd, "hak", "extra.hak", installer="Mod", crc=5)                   # not original

    originals = {fk.file_key for fk in pd.original_file_keys()}
    assert originals == {"hak\\core.hak", "data\\base.bif"}

    changed = {fk.file_key for fk in pd.changed_original_files()}
    assert changed == {"data\\base.bif"}  # only the CRC-mismatched original
