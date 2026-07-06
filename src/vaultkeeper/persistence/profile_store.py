"""Native (JSON) persistence for a ProfileData database.

Replaces the VB BinaryFormatter files with an inspectable JSON store (the hybrid
data strategy: native format going forward; a read-only NRBF importer for legacy
migration lands later). The four dictionaries plus originals and all mod
properties are serialised; the Groups views and the transient Changes are
rebuilt/reset on load. FileKeyInfo round-trips through its full_key.

Enum values are stored as their integer/name value so the JSON is stable and the
schema is versioned (:data:`constants.NATIVE_STORE_VERSION`).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import FileData, InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import GroupStatus, Ratings, State, Weapon
from vaultkeeper.persistence.json_store import read_json, write_json


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _mod_to_dict(md: ModData) -> dict[str, Any]:
    return {
        "group": md.group,
        "mod_name": md.mod_name,
        "group_state": md.group_state.value,
        "install_state": int(md.install_state),
        "mod_state": int(md.mod_state),
        "rating": int(md.rating),
        "level_start": md.level_start,
        "level_end": md.level_end,
        "best_weapon": int(md.best_weapon),
        "hench_count": md.hench_count,
        "web_link": md.web_link,
        "workshop_id": md.workshop_id,
        "date_completed": _dt(md.date_completed),
        "completed_count": md.completed_count,
        "dependencies": list(md.dependencies),
        "files": [fk.full_key for fk in md.files],
    }


def _mod_from_dict(data: dict[str, Any]) -> ModData:
    md = ModData(group=data["group"], mod_name=data.get("mod_name", ""))
    md.group_state = GroupStatus(data.get("group_state", GroupStatus.EXPANDED.value))
    md.install_state = State(data.get("install_state", State.UNKNOWN))
    md.mod_state = State(data.get("mod_state", State.NONE))
    md.rating = Ratings(data.get("rating", Ratings.NONE))
    md.level_start = data.get("level_start", C.NULL_VALUE)
    md.level_end = data.get("level_end", C.NULL_VALUE)
    md.best_weapon = Weapon(data.get("best_weapon", Weapon.NONE))
    md.hench_count = data.get("hench_count", C.NULL_VALUE)
    md.web_link = data.get("web_link", "")
    md.workshop_id = data.get("workshop_id", "")
    md.date_completed = _parse_dt(data.get("date_completed"))
    md.completed_count = data.get("completed_count", 0)
    md.dependencies.extend(data.get("dependencies", []))
    md.files.extend(FileKeyInfo.from_full_key(fk) for fk in data.get("files", []))
    return md


def _file_to_dict(fd: FileData) -> dict[str, Any]:
    return {
        "file_state": int(fd.file_state),
        "extension": fd.extension,
        "modified": _dt(fd.modified),
        "byte_size": fd.byte_size,
        "file_crc": fd.file_crc,
    }


def _installed_to_dict(ifd: InstalledFileData) -> dict[str, Any]:
    data = _file_to_dict(ifd)
    data["installer"] = ifd.installer
    data["mod_files"] = [fk.full_key for fk in ifd.mod_files]
    data["mod_file_conflicts"] = [fk.full_key for fk in ifd.mod_file_conflicts]
    return data


def to_dict(pd: ProfileData) -> dict[str, Any]:
    """Serialise a ProfileData to a JSON-able dict."""
    return {
        "version": C.NATIVE_STORE_VERSION,
        "mods": [_mod_to_dict(md) for md in pd.mod_list.values()],
        "files": {fk.full_key: _file_to_dict(fd) for fk, fd in pd.file_list.items()},
        "installed": {
            fk.full_key: _installed_to_dict(ifd) for fk, ifd in pd.installed_list.items()
        },
        "original_files": {k: v for k, v in pd.original_files.items()},
        "original_ee_files": {k: v for k, v in pd.original_ee_files.items()},
    }


def from_dict(data: dict[str, Any]) -> ProfileData:
    """Reconstruct a ProfileData from a serialised dict."""
    pd = ProfileData()

    for md_data in data.get("mods", []):
        pd.add_mod(_mod_from_dict(md_data))

    for full_key, fd_data in data.get("files", {}).items():
        fk = FileKeyInfo.from_full_key(full_key)
        pd.file_list[fk] = FileData(
            key=fk,
            file_state=State(fd_data["file_state"]),
            extension=fd_data["extension"],
            modified=_parse_dt(fd_data["modified"]),
            byte_size=fd_data["byte_size"],
            file_crc=fd_data["file_crc"],
        )

    for full_key, ifd_data in data.get("installed", {}).items():
        fk = FileKeyInfo.from_full_key(full_key)
        ifd = InstalledFileData(
            key=fk,
            file_state=State(ifd_data["file_state"]),
            extension=ifd_data["extension"],
            modified=_parse_dt(ifd_data["modified"]),
            byte_size=ifd_data["byte_size"],
            file_crc=ifd_data["file_crc"],
            installer=ifd_data.get("installer", C.INSTALLER_UNKNOWN),
        )
        ifd.mod_files.extend(
            FileKeyInfo.from_full_key(k) for k in ifd_data.get("mod_files", [])
        )
        ifd.mod_file_conflicts.extend(
            FileKeyInfo.from_full_key(k) for k in ifd_data.get("mod_file_conflicts", [])
        )
        pd.installed_list[fk] = ifd

    for k, v in data.get("original_files", {}).items():
        pd.original_files[k] = v
    for k, v in data.get("original_ee_files", {}).items():
        pd.original_ee_files[k] = v

    pd.initialise_groups()
    return pd


def save_profile(pd: ProfileData, path: str | Path) -> Path:
    """Persist a ProfileData to ``path`` atomically."""
    return write_json(path, to_dict(pd))


def load_profile(path: str | Path) -> ProfileData | None:
    """Load a ProfileData from ``path``; ``None`` if the file is absent."""
    data = read_json(path, default=None)
    if data is None:
        return None
    return from_dict(data)
