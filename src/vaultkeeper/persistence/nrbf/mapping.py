"""Map parsed NRBF NIT payloads to Vaultkeeper domain objects.

Serialized field names come from ``rehaul/03_DATA_FORMAT_SPEC.md`` §2.2 (VB
auto-properties serialize as ``_PropName`` backing fields; a few explicit fields
like ``LevelStartValue``/``LevelEndtValue`` keep their names — note the "Endt"
typo). Lookups are lenient (missing members default; unknown extras ignored) per
the spec's version-tolerance guidance, so evolving class shapes don't break the
one-time import.

This slice maps FileKeyInfo and ModData (mod properties + groups — the most
important user data). The remaining payloads (FileData/InstalledFileData install
tables, installation sets, workshop, play data) map the same way and are added as
they're needed; the file database can also simply be rebuilt from disk.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any, TypeVar

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import GroupStatus, Ratings, State, Weapon
from vaultkeeper.persistence.nrbf.collections import simplify
from vaultkeeper.persistence.nrbf.reader import NrbfClass, read_nrbf

_E = TypeVar("_E", bound=IntEnum)
_DOTNET_MIN_DATE = datetime(1, 1, 1)


def _enum(enum_cls: type[_E], value: Any, default: _E) -> _E:
    try:
        return enum_cls(int(value))
    except (ValueError, TypeError):
        return default


def map_file_key(obj: NrbfClass) -> FileKeyInfo:
    """Map a serialized FileKeyInfo to a Vaultkeeper FileKeyInfo."""
    m = obj.members
    return FileKeyInfo(
        m.get("_Group", ""),
        m.get("_ModName", ""),
        m.get("_Folder", ""),
        m.get("_Filename", ""),
    )


def map_mod_data(obj: NrbfClass) -> ModData:
    """Map a serialized ModData (mod or group row) to a Vaultkeeper ModData."""
    m = obj.members
    md = ModData(group=m.get("_Group", ""), mod_name=m.get("_ModName", "") or "")
    md.mod_state = _enum(State, m.get("_ModState"), State.NONE)
    md.install_state = _enum(State, m.get("_InstallState"), State.UNKNOWN)
    md.rating = _enum(Ratings, m.get("_Rating"), Ratings.NONE)
    md.best_weapon = _enum(Weapon, m.get("_BestWeapon"), Weapon.NONE)
    md.level_start = m.get("LevelStartValue", C.NULL_VALUE)
    md.level_end = m.get("LevelEndtValue", C.NULL_VALUE)  # note the VB typo
    md.hench_count = m.get("_HenchCount", C.NULL_VALUE)
    md.web_link = m.get("_WebLink", "") or ""
    md.workshop_id = m.get("_WorkshopId", "") or ""
    md.completed_count = m.get("_CompletedCount", 0) or 0

    dc = m.get("_DateCompleted")
    md.date_completed = None if (dc is None or dc == _DOTNET_MIN_DATE) else dc

    # GroupState is a LazWorks Int32 enum; 0 == Expanded, non-zero == Collapsed.
    md.group_state = GroupStatus.EXPANDED if not m.get("_GroupState") else GroupStatus.COLLAPSED

    for fk in m.get("_Files") or []:
        if isinstance(fk, NrbfClass):
            md.files.append(map_file_key(fk))
    for dep in m.get("_Dependencies") or []:
        if isinstance(dep, str):
            md.dependencies.append(dep)
    return md


def map_mod_list(root: Any) -> dict[str, ModData]:
    """Map a serialized ``Dictionary(Of String, ModData)`` to name -> ModData."""
    graph = simplify(root)
    result: dict[str, ModData] = {}
    if isinstance(graph, dict):
        for name, value in graph.items():
            if isinstance(value, NrbfClass):
                result[str(name)] = map_mod_data(value)
    return result


def import_mod_list(data: bytes) -> dict[str, ModData]:
    """Read a serialized NIT ModData file and return name -> ModData."""
    return map_mod_list(read_nrbf(data))
