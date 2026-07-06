"""Round-trip tests for native ProfileData persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import FileData, InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import GroupStatus, Ratings, State, Weapon
from vaultkeeper.persistence.profile_store import (
    from_dict,
    load_profile,
    save_profile,
    to_dict,
)


def _sample() -> ProfileData:
    pd = ProfileData()
    # A group row + a mod with rich properties.
    grp = ModData(group="Adventures")
    grp.group_state = GroupStatus.COLLAPSED
    pd.add_mod(grp)

    md = ModData(group="Adventures", mod_name="Cool Mod")
    md.mod_state = State.INSTALLED
    md.rating = Ratings.EXCELLENT
    md.best_weapon = Weapon.KATANA
    md.level_start = 3
    md.hench_count = 2
    md.web_link = "https://example.test"
    md.workshop_id = "42"
    md.date_completed = datetime(2024, 6, 1, 12, 30)
    md.completed_count = 2
    md.dependencies.append("Other Mod")
    fk = FileKeyInfo("Adventures", "Cool Mod", "hak", "a.hak")
    md.files.append(fk)
    pd.add_mod(md)

    pd.file_list[fk] = FileData(
        key=fk, file_state=State.INSTALLED, extension=".hak",
        modified=datetime(2024, 1, 2), byte_size=99, file_crc=12345,
    )

    ifk = FileKeyInfo.installed("hak", "a.hak")
    ifd = InstalledFileData(
        key=ifk, file_state=State.INSTALLED, extension=".hak",
        modified=datetime(2024, 1, 2), byte_size=99, file_crc=12345,
        installer="Cool Mod",
    )
    ifd.mod_files.append(fk)
    ifd.mod_file_conflicts.append(fk)
    pd.installed_list[ifk] = ifd

    pd.original_files["hak\\core.hak"] = 555
    return pd


def test_roundtrip_in_memory() -> None:
    pd = _sample()
    restored = from_dict(to_dict(pd))

    assert set(restored.mod_keys) == {"Cool Mod"}
    md = restored.mod_item("Cool Mod")
    assert md is not None
    assert md.mod_state == State.INSTALLED
    assert md.rating == Ratings.EXCELLENT
    assert md.best_weapon == Weapon.KATANA
    assert md.level_start == 3
    assert md.hench_count == 2
    assert md.workshop_id == "42"
    assert md.date_completed == datetime(2024, 6, 1, 12, 30)
    assert md.completed_count == 2
    assert md.dependencies == ["Other Mod"]
    assert [fk.full_key for fk in md.files] == [
        FileKeyInfo("Adventures", "Cool Mod", "hak", "a.hak").full_key
    ]


def test_roundtrip_files_and_installed() -> None:
    restored = from_dict(to_dict(_sample()))
    fk = FileKeyInfo("Adventures", "Cool Mod", "hak", "a.hak")
    fd = restored.file_list[fk]
    assert fd.file_crc == 12345
    assert fd.byte_size == 99
    assert fd.modified == datetime(2024, 1, 2)

    ifk = FileKeyInfo.installed("hak", "a.hak")
    ifd = restored.installed_list[ifk]
    assert ifd.installer == "Cool Mod"
    assert ifd.mod_files == [fk]
    assert ifd.mod_file_conflicts == [fk]


def test_originals_and_groups_rebuilt() -> None:
    restored = from_dict(to_dict(_sample()))
    assert restored.original_files["hak\\core.hak"] == 555
    # Groups are rebuilt from the group rows on load.
    assert "Adventures" in restored.groups
    assert restored.groups["Adventures"].member_names == ["Cool Mod"]


def test_save_and_load_file(tmp_path: Path) -> None:
    path = tmp_path / "Data" / "My Mods.json"
    save_profile(_sample(), path)
    assert path.exists()
    restored = load_profile(path)
    assert restored is not None
    assert restored.mod_keys == ["Cool Mod"]  # group row excluded from mod_keys
    # The group row survived with its persisted collapsed state.
    grp_row = restored.mod_list["Adventures"]
    assert grp_row.is_group_item
    assert grp_row.group_state == GroupStatus.COLLAPSED


def test_load_missing_returns_none(tmp_path: Path) -> None:
    assert load_profile(tmp_path / "nope.json") is None


def test_version_stamped() -> None:
    assert to_dict(_sample())["version"] == C.NATIVE_STORE_VERSION
