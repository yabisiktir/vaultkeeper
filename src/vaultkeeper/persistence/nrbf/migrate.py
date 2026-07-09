"""Import a legacy NIT Store into a native Vaultkeeper ``ProfileData``.

The read-only side of the hybrid data strategy (see ``rehaul/03_DATA_FORMAT_SPEC.md``):
a one-time migration that reads the VB app's ``.NET BinaryFormatter`` profile data via
the :mod:`~vaultkeeper.persistence.nrbf` reader and rebuilds a native model.

Store layout (spec §1): ``<store>/Data/<Profile>/nit.ModData_Format_NNN`` holds the
serialized ``Dictionary(Of String, ModData)`` — the user-authored per-mod metadata
(group, rating, weapon, web link, play data, workshop id, file keys). This module
locates that file (VB ``GetLatestDataFile`` — highest version wins) and maps it with
the tested :func:`import_mod_list`.

Only the **ModData** table is imported; the file/install tables are deliberately left
empty so the app rebuilds them from disk on first open (spec's *RebuildRequested*
flow). The other NRBF payloads (FileData/InstallData/InstallationSets/PlayTimeData/
WorkshopContent) can rebuild-from-disk too, so importing them is deferred.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.persistence.nrbf.mapping import import_mod_list

#: VB ``Pdc.DataFilename`` — the fixed prefix of every data file.
_DATA_FILENAME = "nit"
#: VB ``Pdc.DataFormatVersion`` — the current on-disk format; probed downwards.
DATA_FORMAT_VERSION = 2
#: Legacy NIT Store subfolder holding per-profile data (VB ``Paths.C.Data``).
_DATA_DIR = "Data"


def data_file_name(member: str, version: int = DATA_FORMAT_VERSION) -> str:
    """On-disk name for a data file (VB ``ProfileDataExtensions.ToName``).

    ``nit.<Member>_Format_<vvv>`` with a zero-padded 3-digit version and no extension,
    e.g. ``data_file_name("ModData") == "nit.ModData_Format_002"``.
    """
    return f"{_DATA_FILENAME}.{member}_Format_{version:03d}"


def find_latest_data_file(folder: Path, member: str) -> Path | None:
    """Highest-version data file for ``member`` in ``folder`` (VB ``GetLatestDataFile``).

    Probes versions from :data:`DATA_FORMAT_VERSION` down to 1 and returns the first
    that exists, or ``None`` when the member has no data file.
    """
    for version in range(DATA_FORMAT_VERSION, 0, -1):
        candidate = folder / data_file_name(member, version)
        if candidate.is_file():
            return candidate
    return None


def list_profiles(store_root: Path) -> list[str]:
    """Profile names in a NIT Store — the subfolders of ``Data\\`` (sorted)."""
    data_dir = Path(store_root) / _DATA_DIR
    if not data_dir.is_dir():
        return []
    return sorted(p.name for p in data_dir.iterdir() if p.is_dir())


def migrate_profile(store_root: Path, profile_name: str) -> ProfileData:
    """Import a legacy profile's ModData into a fresh native ``ProfileData``.

    Returns a ProfileData with the mod list (and its group rows) populated; the
    file/install tables are left empty for rebuild-from-disk. When the profile has no
    ModData file, an empty ProfileData is returned.
    """
    pd = ProfileData()
    profile_data_dir = Path(store_root) / _DATA_DIR / profile_name
    mod_file = find_latest_data_file(profile_data_dir, "ModData")
    if mod_file is not None:
        for md in import_mod_list(mod_file.read_bytes()).values():
            pd.add_mod(md)
    # Guarantee the reserved None/Installed group rows and (re)build group views —
    # matches the app's load path (a real store's ModData also carries group rows).
    pd.ensure_mandatory_groups()
    return pd
