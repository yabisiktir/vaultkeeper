"""Group and mod-property recovery — restore data from another profile's JSON.

Ports the essence of two VB.NET handlers:

* ``MsRecoverGroups_Click`` (NIT.Menu.vb:4898-5022) + ``ProfileData.GetGroupInfo``
  (ProfileData.vb:1046-1072) — read a Mod Data file and build a Group ->
  [member names] map, then create any missing groups and move mods into their
  recovered group, annealing afterwards.
* ``MsRecoverModProperties_Click`` (NIT.Menu.vb:5077-5125) + ``ProfileData.
  RecoverUserData`` (ProfileData.vb:2730-2789) — read a Mod Data file and copy
  the user-editable properties (Rating, BestWeapon, LevelStart, LevelEnd,
  HenchCount, WebLink) onto the matching mods in the active profile.

The VB source deserialises a BinaryFormatter v2 ModData file
(``Pde.DataFiles.ModData``), either extracted from a Profile Data backup or
browsed for directly. Vaultkeeper's native store is one JSON file per profile
(``<data_dir>/<profile>.json`` — see ``persistence/profile_store.py``), and its
backups (``ProfileController.backup_data``) are just a zip of the whole Data
directory. So the port's recovery source is *another profile's JSON* — a
parsed dict, a path to one, or (via :func:`extract_profile_json_from_zip`) a
path inside a backup zip.

This module is deliberately headless and purely about *reading* that source
(dependency-light: only ``json_store``). The UI-facing ``ProfileController``
methods that apply the result onto the live profile (move mods between
groups, assign properties onto ``ModData``, persist) are layered on top and
kept out of this module by design.

Divergences from VB, noted rather than silently "fixed":

* VB's ``GetGroupInfo`` returns Group -> [member mod names]. The port's
  :func:`read_group_info` returns the inverse Mod -> Group map, which is
  simpler for a caller to apply one mod at a time and is informationally
  equivalent (both are keyed off the same per-mod ``Group``/``group`` field).
* VB's ``RecoverUserData`` (ProfileData.vb:2755-2778) only restores six
  properties: Rating, BestWeapon, LevelStart, LevelEnd, HenchCount, WebLink.
  It does NOT touch DateCompleted/CompletedCount, even though ModData carries
  them. :func:`read_property_info` also extracts ``completed_count`` and
  ``date_completed`` (present on every mod dict in the native store) so
  callers have them available, but an apply step that wants to stay faithful
  to VB's actual behaviour should only assign the six VB-restored fields.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from vaultkeeper.persistence.json_store import read_json

#: User-editable ModData properties captured per mod in the native store.
#: The first six are what VB's RecoverUserData actually restores
#: (ProfileData.vb:2755-2778); the last two are extracted for completeness
#: only (see module docstring).
PROPERTY_KEYS = (
    "rating",
    "level_start",
    "level_end",
    "best_weapon",
    "hench_count",
    "web_link",
    "completed_count",
    "date_completed",
)


def _load_source(source: dict[str, Any] | Path | str) -> dict[str, Any]:
    """Return a parsed profile dict from ``source`` (already a dict, or a path)."""
    if isinstance(source, dict):
        return source
    data = read_json(source, default=None)
    return data or {}


def read_group_info(source: dict[str, Any] | Path | str) -> dict[str, str]:
    """Build a case-preserving ``{mod_name: group}`` map from a source profile.

    Ports the essence of ``ProfileData.GetGroupInfo`` (ProfileData.vb:1046),
    called from ``MsRecoverGroups_Click`` (NIT.Menu.vb:4898). VB deserialises a
    v2 ModData file and returns Group -> [member names], skipping group-item
    placeholder rows (``mdi.IsNotGroupItem``, ProfileData.vb:1065-1067). The
    port reads ``source``'s ``"mods"`` list and returns the inverse Mod ->
    Group map, skipping any entry whose ``mod_name`` is empty — the native
    store's group-item placeholder (see ``ModData.is_group_item`` /
    ``_mod_to_dict`` in ``persistence/profile_store.py``).

    ``source`` may be an already-parsed profile dict, or a path to a
    ``<profile>.json`` file (loaded via
    :func:`vaultkeeper.persistence.json_store.read_json`).
    """
    data = _load_source(source)
    result: dict[str, str] = {}
    for mod in data.get("mods", []):
        name = mod.get("mod_name", "")
        if name == "":
            continue
        result[name] = mod.get("group", "")
    return result


def read_property_info(source: dict[str, Any] | Path | str) -> dict[str, dict[str, Any]]:
    """Build a ``{mod_name: {property: value}}`` map from a source profile.

    Ports the essence of ``ProfileData.RecoverUserData`` (ProfileData.vb:2730),
    called from ``MsRecoverModProperties_Click`` (NIT.Menu.vb:5077). VB
    deserialises a v2 ModData file and, for every mod that still exists in the
    active profile, compares and copies over Rating/BestWeapon/LevelStart/
    LevelEnd/HenchCount/WebLink (ProfileData.vb:2744-2785). The port instead
    returns the raw, still-serialized values (ints/strings/an ISO date string
    or ``None``, as stored in the native JSON — see ``PROPERTY_KEYS``) for
    every real mod in ``source`` (group-item placeholders, ``mod_name ==
    ""``, are skipped). Deciding which mods still exist, comparing values, and
    applying them onto live ``ModData`` (enum coercion, date parsing, exactly
    as ``_mod_from_dict`` does) is left to the calling controller.

    ``source`` may be an already-parsed profile dict, or a path to a
    ``<profile>.json`` file.
    """
    data = _load_source(source)
    result: dict[str, dict[str, Any]] = {}
    for mod in data.get("mods", []):
        name = mod.get("mod_name", "")
        if name == "":
            continue
        result[name] = {key: mod.get(key) for key in PROPERTY_KEYS}
    return result


def extract_profile_json_from_zip(zip_path: Path, profile_name: str, dest_dir: Path) -> Path | None:
    """Extract ``<profile_name>.json`` from a backup zip into ``dest_dir``.

    Faithful to the VB pattern of extracting the chosen Profile Data backup
    and then reading ``<profile>\\ModData`` out of it (``ZipManager.Extract``
    + ``My.Computer.FileSystem.CombinePath``, used in both
    ``MsRecoverGroups_Click`` NIT.Menu.vb:4938-4942 and
    ``MsRecoverModProperties_Click`` NIT.Menu.vb:5101-5111). Vaultkeeper's
    backup zip is a flat dump of the whole Data directory (see
    ``ProfileController.backup_data``), so the equivalent member is simply
    ``<profile_name>.json`` at the zip's top level.

    Returns the extracted file's path, or ``None`` if the zip has no such
    member (mirrors VB's ``recoveryFile.IsNothing`` / failed-extract paths).
    """
    member = f"{profile_name}.json"
    with zipfile.ZipFile(zip_path) as archive:
        if member not in archive.namelist():
            return None
        dest_dir.mkdir(parents=True, exist_ok=True)
        return Path(archive.extract(member, path=dest_dir))
