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

This module reads the aliases headlessly (no Qt). It also exposes a **guarded**
writer (:func:`write_alias_section`, VB ``AliasSectionEditor``) used only by the
Alias-section editor: because ``nwn.ini`` is game config, the writer backs the file
up first and callers MUST obtain an explicit user confirmation before invoking it
(the config-isolation stance — see :mod:`vaultkeeper.game.config_guard`). Nothing on
the normal read/scan path ever writes ``nwn.ini``.
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


def nwn_ini_path(user_dir: Path) -> Path:
    """The ``nwn.ini`` path for a user-files folder."""
    return Path(user_dir) / "nwn.ini"


def read_alias_section(user_dir: Path) -> list[tuple[str, str]]:
    """Raw ``[Alias]`` ``key`` / ``value`` pairs in file order (VB editor's ListView).

    Unlike :func:`read_alias_locations`, this preserves the original key case and the
    literal (unresolved) value, and keeps *every* alias entry (including ``SAVES``),
    so the editor shows exactly what is in the file. A missing/unreadable ``nwn.ini``
    yields ``[]``.
    """
    try:
        text = nwn_ini_path(user_dir).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    rows: list[tuple[str, str]] = []
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
        key = key.strip()
        if key:
            rows.append((key, value.strip()))
    return rows


def write_alias_section(
    user_dir: Path, updates: dict[str, str], *, backup: bool = True
) -> int:
    """Update ``[Alias]`` key values in ``nwn.ini`` in place (VB ``SaveNwnIniFile``).

    CONFIG-ISOLATION: ``nwn.ini`` is game config — the caller MUST have obtained an
    explicit user confirmation before calling this. The original file is copied to
    ``nwn.ini.bak`` once (never overwritten) before the first write so the user can
    always recover it.

    ``updates`` maps an alias key (matched case-insensitively) to its new value; only
    keys that already exist in the ``[Alias]`` section are changed (unknown keys are
    ignored). Every other line — sections, comments, spacing, line endings — is left
    byte-for-byte intact. Returns the number of keys actually changed (a value equal to
    the existing one is not counted and not rewritten). Raises ``FileNotFoundError`` if
    ``nwn.ini`` does not exist.
    """
    import shutil

    ini_path = nwn_ini_path(user_dir)
    if not ini_path.is_file():
        raise FileNotFoundError(ini_path)

    wanted = {k.lower(): v for k, v in updates.items()}
    text = ini_path.read_text(encoding="utf-8", errors="replace")
    out_lines: list[str] = []
    in_section = False
    changed = 0
    for raw in text.splitlines(keepends=True):
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped[1:-1].strip().lower() == _ALIAS_SECTION
            out_lines.append(raw)
            continue
        if in_section and "=" in stripped and not stripped.startswith((";", "#")):
            key, _, value = raw.partition("=")
            lookup = key.strip().lower()
            if lookup in wanted:
                new_value = wanted[lookup]
                if value.strip() != new_value:
                    eol = raw[len(raw.rstrip("\r\n")):]
                    out_lines.append(f"{key}={new_value}{eol}")
                    changed += 1
                    continue
        out_lines.append(raw)

    if changed:
        if backup:
            bak = ini_path.with_name(ini_path.name + ".bak")
            if not bak.exists():
                shutil.copy2(ini_path, bak)
        ini_path.write_text("".join(out_lines), encoding="utf-8")
    return changed
