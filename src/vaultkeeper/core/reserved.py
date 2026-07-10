"""Reserved name / prefix rules (VB ``Paths.IsReservedNameOrPrefix``).

NIT reserves a handful of file/folder names, group names and prefixes for its own
use; a user-supplied mod, file or folder name must not collide with them. This is the
headless port of ``Paths.IsReservedNameOrPrefix`` (Paths.vb:805) — consumed by the
name editors (DocOrganiser rename, etc.) via :mod:`vaultkeeper.core.name_edit`.

Matching is case-insensitive throughout (VB ``StringComparer.CurrentCultureIgnoreCase``
/ ``Option Compare Text``).
"""

from __future__ import annotations

from vaultkeeper.core import constants as C

#: Exact reserved names (VB ``Paths.ReservedNames`` keys, Paths.vb:874). ``Installer``
#: = ``.Mod Installer``; the ``Mod*`` markers are Pdc display strings.
_RESERVED_NAMES: frozenset[str] = frozenset(
    n.lower()
    for n in (
        C.MOD_INSTALLER_DIR,
        C.DOWNLOADS_DIR,
        C.HISTORY_DIR,
        C.PUBLISHED_DIR,
        C.WORKSHOP_DIR,
        C.PLAY_TIME_FILE,
        C.WIZARD_FILE,
        "Unknown source",  # Pdc.ModUnknown (ProfileData.Defs.vb:107)
        "Saved character",  # Pdc.ModCharacter (ProfileData.Defs.vb:123)
    )
)

#: Reserved group names (VB ``ReservedGroupNames``, Paths.vb:889).
_RESERVED_GROUP_NAMES: frozenset[str] = frozenset(
    n.lower()
    for n in (
        "799.  Mods Installed by NWN",  # Pdc.OriginalModsGroup
        "820.  Steam Workshop",  # Pdc.WorkshopGroup
        "000.  Restorers",  # Pdc.RestorerGroup
    )
)

#: Reserved prefixes (VB ``ReservedNamePrefixes``, Paths.vb:897). ``ModOriginal`` =
#: the "Neverwinter Nights installation" marker.
_RESERVED_PREFIXES: tuple[str, ...] = tuple(
    p.lower()
    for p in (
        C.INSTALLER_ORIGINAL,  # Pdc.ModOriginal
        C.PLAY_TIME_FILE,
        C.WIZARD_FILE,
    )
)

_AUTO_SUFFIX = "(auto)"


def is_reserved_name_or_prefix(name: str) -> bool:
    """True if ``name`` is a reserved name/group, ends ``(Auto)`` or has a reserved prefix.

    Faithful port of ``Paths.IsReservedNameOrPrefix`` (Paths.vb:805).
    """
    lower = name.lower()
    if (
        lower in _RESERVED_NAMES
        or lower in _RESERVED_GROUP_NAMES
        or lower.endswith(_AUTO_SUFFIX)
    ):
        return True
    return any(lower.startswith(prefix) for prefix in _RESERVED_PREFIXES)
