"""Tests for mapping NRBF NIT payloads to Vaultkeeper domain objects.

The mapping logic is validated against hand-built NrbfClass graphs (byte parsing
is covered separately), using the serialized field names from the format spec.
"""

from __future__ import annotations

from datetime import datetime

from vaultkeeper.core import constants as C
from vaultkeeper.core.state import GroupStatus, Ratings, State, Weapon
from vaultkeeper.persistence.nrbf.mapping import map_file_key, map_mod_data, map_mod_list
from vaultkeeper.persistence.nrbf.reader import NrbfClass


def _file_key(group: str, mod: str, folder: str, filename: str) -> NrbfClass:
    return NrbfClass(
        "FileKeyInfo",
        "NWN Installer Tool",
        {"_Group": group, "_ModName": mod, "_Folder": folder, "_Filename": filename},
    )


def test_map_file_key() -> None:
    fk = map_file_key(_file_key("G", "Mod", "hak", "a.hak"))
    assert fk.group == "G"
    assert fk.mod_name == "Mod"
    assert fk.file_key == "hak\\a.hak"


def test_map_mod_data_full() -> None:
    obj = NrbfClass(
        "ModData",
        "NWN Installer Tool",
        {
            "_Group": "Adventures",
            "_ModName": "Cool Mod",
            "_ModState": int(State.INSTALLED),
            "_InstallState": int(State.UNKNOWN),
            "_Rating": int(Ratings.EXCELLENT),
            "_BestWeapon": int(Weapon.KATANA),
            "LevelStartValue": 3,
            "LevelEndtValue": 10,
            "_HenchCount": 2,
            "_WebLink": "https://example.test",
            "_WorkshopId": "42",
            "_CompletedCount": 2,
            "_DateCompleted": datetime(2020, 6, 1),
            "_GroupState": 1,  # collapsed
            "_Files": [_file_key("Adventures", "Cool Mod", "hak", "a.hak")],
            "_Dependencies": ["Other Mod"],
        },
    )
    md = map_mod_data(obj)
    assert md.group == "Adventures"
    assert md.mod_name == "Cool Mod"
    assert md.mod_state == State.INSTALLED
    assert md.rating == Ratings.EXCELLENT
    assert md.best_weapon == Weapon.KATANA
    assert md.level_start == 3
    assert md.level_end == 10
    assert md.hench_count == 2
    assert md.web_link == "https://example.test"
    assert md.workshop_id == "42"
    assert md.completed_count == 2
    assert md.date_completed == datetime(2020, 6, 1)
    assert md.group_state == GroupStatus.COLLAPSED
    assert len(md.files) == 1
    assert md.files[0].file_key == "hak\\a.hak"
    assert md.dependencies == ["Other Mod"]


def test_map_mod_data_group_row_and_defaults() -> None:
    obj = NrbfClass("ModData", "NWN Installer Tool", {"_Group": "MyGroup", "_ModName": ""})
    md = map_mod_data(obj)
    assert md.is_group_item
    assert md.mod_state == State.NONE  # default
    assert md.level_start == C.NULL_VALUE
    assert md.date_completed is None  # missing -> None


def test_map_mod_data_mindate_is_none() -> None:
    obj = NrbfClass(
        "ModData",
        "NWN Installer Tool",
        {"_Group": "G", "_ModName": "M", "_DateCompleted": datetime(1, 1, 1)},
    )
    assert map_mod_data(obj).date_completed is None  # Date.MinValue -> None


def test_map_mod_list() -> None:
    a = NrbfClass("ModData", "L", {"_Group": "G", "_ModName": "Alpha"})
    b = NrbfClass("ModData", "L", {"_Group": "G", "_ModName": "Beta"})
    # A simplified dict graph (what simplify() would produce for the ModList dict).
    result = map_mod_list({"Alpha": a, "Beta": b})
    assert set(result) == {"Alpha", "Beta"}
    assert result["Alpha"].mod_name == "Alpha"
