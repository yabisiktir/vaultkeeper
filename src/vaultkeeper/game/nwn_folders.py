"""Resolve NWN folder locations from ``nwn.ini`` — port of ``NwnFolderInfo``.

The original tool learns where each moddable NWN folder physically lives by
reading the ``[Alias]`` section of ``nwn.ini`` (``NwnFolderInfo.PopulateLocations``,
``NwnFolderInfo.vb:319``): each alias key (``HAK``, ``TLK``, ``OVERRIDE``,
``MODULES``, ``AMBIENT`` …) maps to a fully-qualified folder, resolved relative to
the *NWN User Files* folder. On NWN:EE those all sit under the user dir
(``~/Documents/Neverwinter Nights``), while the base-game ``data`` sub-folders
(``mod``/``nwm``/``mus``/``txpk``) and ``ovr`` live under the install dir. Without
these locations the app looks for installed files in the wrong place and reports
every mod as not-installed (see the EE branch of :meth:`Mapper.nwn_folder_paths`).

This module reads the aliases headlessly (no Qt); it never writes ``nwn.ini``
(the tool's config-isolation stance — see :mod:`vaultkeeper.game.config_guard`).
"""

from __future__ import annotations

from pathlib import Path

#: The ``[Alias]`` section name that holds folder locations.
_ALIAS_SECTION = "alias"

#: Alias keys that are not moddable folder locations (VB skips these in
#: ``PopulateLocations``): the CD/hard-drive markers and the game-saves entry
#: (saves are resolved separately via ``SetGameSavesPath``).
_SKIP_KEYS = frozenset({"cd0", "hd0", "saves"})

#: VB ``NwnFolderInfo.NwmKey`` — the ini key for the modules-movies folder is
#: ``NWMFiles`` but the folder identifier the rest of the app uses is ``nwm``.
_NWM_INI_KEY = "nwmfiles"
_NWM_FOLDER = "nwm"


def read_alias_locations(user_dir: Path) -> dict[str, Path]:
    """Folder locations from ``<user_dir>/nwn.ini``'s ``[Alias]`` section.

    Returns ``{folder_key_lower: absolute Path}``. Missing/unreadable ``nwn.ini``
    yields an empty dict (the caller falls back to standard folder layout).
    Values are resolved against ``user_dir`` (an absolute value is used as-is,
    matching ``FileSystem.CombinePath``). The ``NWMFiles`` key is normalised to
    the ``nwm`` folder identifier (VB ``PopulateLocations``).
    """
    ini_path = Path(user_dir) / "nwn.ini"
    try:
        text = ini_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    locations: dict[str, Path] = {}
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line[1:-1].strip().lower() == _ALIAS_SECTION
            continue
        if not in_section or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if not key or not value or key in _SKIP_KEYS:
            continue
        if key == _NWM_INI_KEY:
            key = _NWM_FOLDER
        # CombinePath(user_dir, value): an absolute value wins, else join.
        candidate = Path(value)
        locations[key] = candidate if candidate.is_absolute() else Path(user_dir) / value
    return locations
