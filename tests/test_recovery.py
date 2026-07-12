"""Tests for group/mod-property recovery (game/recovery.py)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from vaultkeeper.game.recovery import (
    extract_profile_json_from_zip,
    read_group_info,
    read_property_info,
)
from vaultkeeper.persistence.json_store import write_json


def _mod(name: str, group: str, **overrides: Any) -> dict[str, Any]:
    """A profile-store mod dict (see persistence/profile_store.py:_mod_to_dict)."""
    base: dict[str, Any] = {
        "group": group,
        "mod_name": name,
        "group_state": "expanded",
        "install_state": 0,
        "mod_state": 0,
        "rating": 0,
        "level_start": -1,
        "level_end": -1,
        "best_weapon": 0,
        "hench_count": -1,
        "web_link": "",
        "workshop_id": "",
        "date_completed": None,
        "completed_count": 0,
        "dependencies": [],
        "files": [],
    }
    base.update(overrides)
    return base


def _group_item(name: str) -> dict[str, Any]:
    """A group-row placeholder (mod_name == "")."""
    return _mod("", name)


def _sample_profile() -> dict[str, Any]:
    return {
        "version": 1,
        "mods": [
            _group_item("Weapons"),
            _mod(
                "Excalibur",
                "Weapons",
                rating=1,
                level_start=5,
                level_end=15,
                best_weapon=4,
                hench_count=2,
                web_link="https://example.com/excalibur",
                completed_count=3,
                date_completed="2024-01-02T03:04:05",
            ),
            _mod(
                "Dragon Slayer",
                "Weapons",
                rating=2,
                level_start=10,
                level_end=20,
                best_weapon=12,
                hench_count=0,
                web_link="",
                completed_count=0,
                date_completed=None,
            ),
            _group_item("Companions"),
            _mod(
                "Faithful Hound",
                "Companions",
                rating=3,
                level_start=1,
                level_end=-1,
                best_weapon=0,
                hench_count=1,
                web_link="https://example.com/hound",
                completed_count=1,
                date_completed="2023-06-15T00:00:00",
            ),
        ],
        "files": {},
        "installed": {},
        "original_files": {},
        "original_ee_files": {},
    }


class TestReadGroupInfo:
    def test_maps_mod_to_group_excluding_placeholders(self) -> None:
        info = read_group_info(_sample_profile())
        assert info == {
            "Excalibur": "Weapons",
            "Dragon Slayer": "Weapons",
            "Faithful Hound": "Companions",
        }

    def test_case_preserving(self) -> None:
        info = read_group_info(_sample_profile())
        # Keys and values keep their original casing (no lowercasing/uppercasing).
        assert "Excalibur" in info
        assert info["Excalibur"] == "Weapons"
        assert "excalibur" not in info

    def test_reads_from_path(self, tmp_path: Path) -> None:
        profile_path = tmp_path / "MyProfile.json"
        write_json(profile_path, _sample_profile())
        info = read_group_info(profile_path)
        assert info == {
            "Excalibur": "Weapons",
            "Dragon Slayer": "Weapons",
            "Faithful Hound": "Companions",
        }

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert read_group_info(tmp_path / "does-not-exist.json") == {}


class TestReadPropertyInfo:
    def test_maps_mod_to_properties_excluding_placeholders(self) -> None:
        info = read_property_info(_sample_profile())
        assert set(info) == {"Excalibur", "Dragon Slayer", "Faithful Hound"}
        assert info["Excalibur"] == {
            "rating": 1,
            "level_start": 5,
            "level_end": 15,
            "best_weapon": 4,
            "hench_count": 2,
            "web_link": "https://example.com/excalibur",
            "completed_count": 3,
            "date_completed": "2024-01-02T03:04:05",
        }
        assert info["Dragon Slayer"]["rating"] == 2
        assert info["Dragon Slayer"]["date_completed"] is None
        assert info["Faithful Hound"]["level_end"] == -1

    def test_reads_from_path(self, tmp_path: Path) -> None:
        profile_path = tmp_path / "MyProfile.json"
        write_json(profile_path, _sample_profile())
        info = read_property_info(profile_path)
        assert info["Faithful Hound"] == {
            "rating": 3,
            "level_start": 1,
            "level_end": -1,
            "best_weapon": 0,
            "hench_count": 1,
            "web_link": "https://example.com/hound",
            "completed_count": 1,
            "date_completed": "2023-06-15T00:00:00",
        }

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert read_property_info(tmp_path / "does-not-exist.json") == {}


class TestExtractProfileJsonFromZip:
    def test_extracts_matching_member(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "backup.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("MyProfile.json", '{"mods": []}')
            archive.writestr("OtherProfile.json", '{"mods": []}')

        dest_dir = tmp_path / "extracted"
        result = extract_profile_json_from_zip(zip_path, "MyProfile", dest_dir)

        assert result == dest_dir / "MyProfile.json"
        assert result.read_text() == '{"mods": []}'

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "backup.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("OtherProfile.json", '{"mods": []}')

        dest_dir = tmp_path / "extracted"
        result = extract_profile_json_from_zip(zip_path, "MyProfile", dest_dir)

        assert result is None

    def test_extracted_file_readable_by_read_group_info(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "backup.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("SourceProfile.json", json.dumps(_sample_profile()))

        dest_dir = tmp_path / "extracted"
        result = extract_profile_json_from_zip(zip_path, "SourceProfile", dest_dir)

        assert result is not None
        assert read_group_info(result) == {
            "Excalibur": "Weapons",
            "Dragon Slayer": "Weapons",
            "Faithful Hound": "Companions",
        }
