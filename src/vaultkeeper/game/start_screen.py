"""NWN Start Screen ("loadscreen") image management — headless model.

Ported from VB ``StartScreenManager.vb`` and ``StartScreenInfo.vb``. NIT lets the
user manage the image NWN shows on its main menu (the *start screen*, historically
called the *loadscreen*). The images live in a dedicated NIT-managed mod::

    <profile mods>/NWN Loadscreens (NIT Managed)/Loadscreen Images/*.tga

and the currently-installed one is written to the game ``override`` folder as
``gui_pre_bknd3.tga``. Which image is "active" is tracked in a per-profile info
file (``StartscreenInfo.txt``) alongside the auto-exclusion list.

This module is the **read-only** core: it locates the managed images and reports
which one is active/installed. The *actions* — add-from-folder, add-from-hak,
install/uninstall/anneal of the loadscreen mod, the slideshow, and the prefix
system — are deferred (see the controller / dialog notes). The extract-from-hak
seam is ready via :mod:`vaultkeeper.core.formats.erf_reader`.

Data contract verified against the VB source:

* ``Pdc.AutoLoadscreen`` = ``"NWN Loadscreens (NIT Managed)"`` (ProfileData.Defs.vb:232)
* ``Pdc.AutoGroup``      = ``"ZZZ.  NIT Managed Restorers (Auto)"`` (ProfileData.Defs.vb:227)
* ``ScreenFolder``       = ``"Loadscreen Images"`` (StartScreenManager.vb:68)
* ``NwnStartScreenName`` = ``"gui_pre_bknd3.tga"`` (StartScreenInfo.vb:44)
* ``Mapper.C.ModOverrideFolder`` = ``"override"`` (Mapper.vb:116)
* ``StartscreenInfo.txt`` in ``Paths.ProfileData`` — 4 lines (StartScreenInfo.vb:126-230):
  0 = active type index ("1" = Standard, "2" = Prefixed),
  1 = Standard display name, 2 = Prefixed display name, 3 = last browse folder.
* ``LoadscreenAutoExcludes.txt`` in ``Paths.ProfileData`` — excluded display names.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import cmp_to_key
from pathlib import Path

from vaultkeeper.core.win_sort import win_compare

# -- Constants (verified against the VB, see module docstring) ------------- #

#: The NIT-managed mod holding the loadscreen images (``Pdc.AutoLoadscreen``).
LOADSCREEN_MOD = "NWN Loadscreens (NIT Managed)"
#: The auto group the loadscreen mod is created under (``Pdc.AutoGroup``).
AUTO_GROUP = "ZZZ.  NIT Managed Restorers (Auto)"
#: The folder inside the mod that contains the image files (``ScreenFolder``).
SCREEN_FOLDER = "Loadscreen Images"
#: NWN's start-screen filename in the game ``override`` folder.
NWN_START_SCREEN_NAME = "gui_pre_bknd3.tga"
#: The game folder the start screen is installed to (``Mapper.C.ModOverrideFolder``).
OVERRIDE_FOLDER = "override"
#: Loadscreen images are TGA files.
IMAGE_EXTENSION = ".tga"

#: Per-profile info file names (relative to ``Paths.ProfileData``).
INFO_FILENAME = "StartscreenInfo.txt"
AUTO_EXCLUDES_FILENAME = "LoadscreenAutoExcludes.txt"
SCREEN_LIST_FILENAME = "LoadscreenFiles.txt"

# ``StartScreenInfo.ScreenType`` index values written to line 0 of the info file.
_TYPE_STANDARD = "1"
_TYPE_PREFIXED = "2"


@dataclass(frozen=True)
class StartScreenInfo:
    """Parsed contents of ``StartscreenInfo.txt`` (VB ``StartScreenInfo.InfoFile``)."""

    active_type: str
    standard: str
    prefixed: str
    browse_folder: str

    @property
    def standard_active(self) -> bool:
        """True when the Standard screen is the active one (VB ``StandardActive``)."""
        return self.active_type == _TYPE_STANDARD

    @property
    def prefix_active(self) -> bool:
        """True when the Prefixed screen is the active one (VB ``PrefixActive``)."""
        return self.active_type == _TYPE_PREFIXED

    @property
    def active_screen(self) -> str:
        """The active loadscreen display name (VB ``ActiveScreen``)."""
        return self.standard if self.standard_active else self.prefixed


@dataclass(frozen=True)
class LoadscreenImage:
    """A single managed loadscreen image file."""

    name: str
    path: Path
    size: int
    excluded: bool
    active: bool


def read_start_screen_info(profile_data_dir: Path) -> StartScreenInfo | None:
    """Read ``StartscreenInfo.txt`` from a profile's data folder.

    Returns ``None`` when the info file does not exist (the manager has never been
    set up for this profile). Missing trailing lines default to ``""`` so a
    truncated file never raises (VB reads the list and indexes it directly, but a
    valid file always holds the 4 slots).
    """
    info_file = profile_data_dir / INFO_FILENAME
    if not info_file.is_file():
        return None
    try:
        lines = info_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    padded = (lines + ["", "", "", ""])[:4]
    active_type, standard, prefixed, browse_folder = padded
    # An empty/blank active-type line defaults to Standard (VB writes "1" on Create).
    if active_type not in (_TYPE_STANDARD, _TYPE_PREFIXED):
        active_type = _TYPE_STANDARD
    return StartScreenInfo(
        active_type=active_type,
        standard=standard,
        prefixed=prefixed,
        browse_folder=browse_folder,
    )


def read_auto_excludes(profile_data_dir: Path) -> list[str]:
    """Read the auto-exclusion display-name list (VB ``AutoExcludes``)."""
    excludes_file = profile_data_dir / AUTO_EXCLUDES_FILENAME
    if not excludes_file.is_file():
        return []
    try:
        text = excludes_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.strip()]


def save_auto_excludes(profile_data_dir: Path, excludes: Iterable[str]) -> None:
    """Persist the auto-exclusion display-name list (VB ``SaveAutoExcludes``).

    VB sorts with ``WindowsSorter`` then writes ``Distinct`` names. We reproduce
    both: Windows natural sort (``win_compare``) followed by an order-preserving
    dedup (ordinal, matching .NET ``String`` equality).
    """
    names = [str(name) for name in excludes]
    names.sort(key=cmp_to_key(win_compare))
    seen: set[str] = set()
    deduped: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            deduped.append(name)

    profile_data_dir.mkdir(parents=True, exist_ok=True)
    (profile_data_dir / AUTO_EXCLUDES_FILENAME).write_text(
        "\n".join(deduped) + ("\n" if deduped else ""),
        encoding="utf-8",
    )


def scan_loadscreens(
    image_folder: Path,
    *,
    active: str = "",
    excludes: object = (),
) -> list[LoadscreenImage]:
    """List the ``.tga`` images in ``image_folder``, Windows-sorted by name.

    The display name is the file name including the ``.tga`` extension (VB's
    ``FvImages`` combines the display name directly onto ``ImageFolder``). ``active``
    marks the currently-active image; ``excludes`` marks auto-excluded images. Both
    comparisons are case-insensitive, matching VB's ``Option Compare Text``.
    """
    if not image_folder.is_dir():
        return []

    exclude_set = {str(name).lower() for name in excludes}
    active_lower = active.lower()

    entries: list[LoadscreenImage] = []
    for entry in image_folder.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() != IMAGE_EXTENSION:
            continue
        try:
            size = entry.stat().st_size
        except OSError:
            size = 0
        name = entry.name
        entries.append(
            LoadscreenImage(
                name=name,
                path=entry,
                size=size,
                excluded=name.lower() in exclude_set,
                active=name.lower() == active_lower,
            )
        )

    entries.sort(key=cmp_to_key(lambda a, b: win_compare(a.name, b.name)))
    return entries
