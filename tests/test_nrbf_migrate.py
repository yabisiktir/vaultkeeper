"""Tests for the NIT Store migration wiring (persistence/nrbf/migrate.py).

Covers data-file naming/discovery (VB GetLatestDataFile) and the migrate_profile
orchestration that turns a legacy profile's ModData into a native ProfileData. The
NRBF parser itself is tested in test_nrbf*.py, so migrate_profile's parse step is
exercised through a stubbed import_mod_list.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.persistence.nrbf import migrate
from vaultkeeper.persistence.nrbf.migrate import (
    data_file_name,
    find_latest_data_file,
    list_profiles,
    migrate_profile,
)


def _profile_data_dir(store: Path, name: str) -> Path:
    d = store / "Data" / name
    d.mkdir(parents=True)
    return d


# -- Naming / discovery (VB GetLatestDataFile) ---------------------------- #


def test_data_file_name_format():
    assert data_file_name("ModData") == "nit.ModData_Format_002"
    assert data_file_name("InstallData", 1) == "nit.InstallData_Format_001"


def test_find_latest_prefers_highest_version(tmp_path):
    folder = tmp_path / "P"
    folder.mkdir()
    (folder / "nit.ModData_Format_001").write_bytes(b"v1")
    (folder / "nit.ModData_Format_002").write_bytes(b"v2")
    assert find_latest_data_file(folder, "ModData").name == "nit.ModData_Format_002"


def test_find_latest_falls_back_to_older_version(tmp_path):
    folder = tmp_path / "P"
    folder.mkdir()
    (folder / "nit.ModData_Format_001").write_bytes(b"v1")
    assert find_latest_data_file(folder, "ModData").name == "nit.ModData_Format_001"


def test_find_latest_absent_is_none(tmp_path):
    folder = tmp_path / "P"
    folder.mkdir()
    assert find_latest_data_file(folder, "ModData") is None


def test_list_profiles(tmp_path):
    _profile_data_dir(tmp_path, "Main")
    _profile_data_dir(tmp_path, "Testing")
    # A store-wide data file (not a profile) sits directly in Data\.
    (tmp_path / "Data" / "nit.OriginalData_Format_002").write_bytes(b"x")
    assert list_profiles(tmp_path) == ["Main", "Testing"]


def test_list_profiles_no_store(tmp_path):
    assert list_profiles(tmp_path / "missing") == []


# -- migrate_profile orchestration ---------------------------------------- #


def test_migrate_profile_builds_profile_data(tmp_path, monkeypatch):
    data_dir = _profile_data_dir(tmp_path, "Main")
    (data_dir / "nit.ModData_Format_002").write_bytes(b"fake-nrbf")

    imported = {
        "Alpha": ModData(group="Adventures", mod_name="Alpha"),
        "Beta": ModData(group="Adventures", mod_name="Beta"),
    }
    monkeypatch.setattr(migrate, "import_mod_list", lambda data: imported)

    pd = migrate_profile(tmp_path, "Main")
    assert set(pd.mod_keys) == {"Alpha", "Beta"}
    assert pd.mod_item("Alpha").group == "Adventures"
    # The reserved group rows exist after migration (like the app's load path).
    from vaultkeeper.core import constants as C

    for group in C.MANDATORY_GROUPS:
        assert group in pd.groups


def test_migrate_profile_reads_the_discovered_file(tmp_path, monkeypatch):
    data_dir = _profile_data_dir(tmp_path, "Main")
    (data_dir / "nit.ModData_Format_002").write_bytes(b"PAYLOAD")

    seen: list[bytes] = []

    def _capture(data: bytes) -> dict:
        seen.append(data)
        return {}

    monkeypatch.setattr(migrate, "import_mod_list", _capture)
    migrate_profile(tmp_path, "Main")
    assert seen == [b"PAYLOAD"]


def test_migrate_profile_without_data_is_empty(tmp_path):
    _profile_data_dir(tmp_path, "Main")  # no ModData file
    pd = migrate_profile(tmp_path, "Main")
    assert list(pd.mod_keys) == []
