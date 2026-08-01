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
seam is ready via :mod:`nwnfile.formats.erf_reader`.

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

from nwnfile.win_sort import win_compare

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
PREFIX_FILENAME = "LoadscreenPrefixes.txt"

#: A prefix line beginning with this char is defined-but-disabled (VB InactivePrefix).
_INACTIVE_PREFIX = "!"

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
    prefixed: bool = False
    filter_prefixed: bool = False


# -- Prefix subsystem (VB StartScreenInfo prefix methods) ------------------ #


def read_prefixes(profile_data_dir: Path) -> dict[str, bool]:
    """Read the defined start-screen prefixes (VB ``GetStartScreenPrefixes``).

    Each line of ``LoadscreenPrefixes.txt`` is a prefix; a leading ``!`` marks it
    defined-but-disabled. Returns a case-insensitive map ``prefix (lowercased) ->
    enabled``. Blank lines are skipped (VB would throw on one and end up with no
    prefixes; skipping yields the sensible result and matches the port's readers).
    """
    prefix_file = profile_data_dir / PREFIX_FILENAME
    if not prefix_file.is_file():
        return {}
    try:
        lines = prefix_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    prefixes: dict[str, bool] = {}
    for line in lines:
        if not line.strip():
            continue
        enabled = line[0] != _INACTIVE_PREFIX
        key = line.lstrip(_INACTIVE_PREFIX)
        prefixes[key.lower()] = enabled
    return prefixes


def get_next_name(available: list[str], active_name: str) -> str:
    """The next available screen name after removing ``active_name`` (VB ``GetNextName``).

    ``available`` is the eligible-screen list (standard or prefixed, already filtered).
    Returns ``""`` when ``active_name`` isn't in the list or it's the only entry
    (VB ``index = -1 Or count = 1``); otherwise the name at the same index after
    removal, wrapping to the front when that index falls off the end.
    """
    if active_name not in available or len(available) == 1:
        return ""
    idx = available.index(active_name)
    rest = available[:idx] + available[idx + 1 :]
    if idx >= len(rest):
        idx = 0
    return rest[idx]


def file_prefix(name: str) -> str:
    """The characters before the first space in ``name`` (VB ``FilePrefix``)."""
    idx = name.find(" ")
    return name[:idx] if idx != -1 else name


def is_prefixed(name: str, prefixes: dict[str, bool]) -> bool:
    """True when ``name``'s prefix is one of the defined prefixes (VB ``IsPrefixed``)."""
    return file_prefix(name).lower() in prefixes


def is_filter_prefixed(name: str, prefixes: dict[str, bool]) -> bool:
    """True when ``name``'s prefix is defined AND enabled (VB ``IsFilterPrefixed``)."""
    key = file_prefix(name).lower()
    return prefixes.get(key, False)


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


def with_active_screen(
    info: StartScreenInfo, name: str, *, prefixed: bool
) -> StartScreenInfo:
    """Return ``info`` with ``name`` set as the active screen (VB ``ActiveScreen`` setter).

    Mirrors VB's on-close update (StartScreenManager.vb:866-873): set the active
    *type* to Prefixed or Standard, then assign the active screen name into the
    matching slot (the ``ActiveScreen`` setter writes ``Standard`` or ``Prefixed``
    depending on which type is active).
    """
    from dataclasses import replace

    if prefixed:
        return replace(info, active_type=_TYPE_PREFIXED, prefixed=name)
    return replace(info, active_type=_TYPE_STANDARD, standard=name)


def cleared_active_screen(info: StartScreenInfo) -> StartScreenInfo:
    """Return ``info`` with both screen names blanked and Standard active (VB delete-all)."""
    from dataclasses import replace

    return replace(info, active_type=_TYPE_STANDARD, standard="", prefixed="")


def save_start_screen_info(profile_data_dir: Path, info: StartScreenInfo) -> None:
    """Persist ``StartscreenInfo.txt`` from ``info`` (VB ``StartScreenInfo.SaveInfo``).

    Writes the 4-line info file (active type / standard name / prefixed name / last
    browse folder), matching the port's other text writers (trailing newline). The VB
    ``InfoFile`` is a 4-element list written with ``ToTextLines``.
    """
    lines = [info.active_type, info.standard, info.prefixed, info.browse_folder]
    profile_data_dir.mkdir(parents=True, exist_ok=True)
    (profile_data_dir / INFO_FILENAME).write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def add_image_target_name(source_name: str, source_dir: Path) -> str:
    """The target image filename for an added source file (VB ``ProcessFiles`` @2161).

    Normally the target keeps the source file name. But a file literally named
    ``gui_pre_bknd3.tga`` (NWN's own start-screen filename) can't be stored under
    that reserved name, so VB derives a meaningful name from the folder it came out
    of: it walks up past any ``override``/``ovr``/``.Mod Installer`` wrapper folders
    and uses ``<folder>.tga`` (or ``<immediate parent>.tga`` if it walked to the
    drive root).
    """
    if source_name.lower() != NWN_START_SCREEN_NAME.lower():
        return source_name

    bad_folders = {OVERRIDE_FOLDER.lower(), "ovr", ".mod installer"}
    folder = source_dir
    immediate = source_dir.name
    # Walk up past wrapper folders (VB While badFolderNames.Contains(folder.Name)).
    while folder.name and folder.name.lower() in bad_folders:
        folder = folder.parent
    # ``folder.name == ""`` means we reached the filesystem root (VB rootName match).
    if not folder.name:
        return f"{immediate}.tga"
    return f"{folder.name}.tga"


def validate_loadscreen_name(
    name: str,
    *,
    initial: str,
    existing: Iterable[str],
) -> tuple[bool, str]:
    """Validate a proposed loadscreen image name (VB ``ValidateName`` @2257).

    Returns ``(ok, value)`` where ``value`` is the normalised name on success or the
    exact VB status message on failure. Rules (in VB order): trim trailing dots;
    reject blank; append ``.tga`` when no extension; reject the reserved
    ``gui_pre_bknd3.tga`` / any :func:`is_reserved_name_or_prefix`; require the
    ``.tga`` extension; reject an unchanged name (case-sensitive); reject a
    case-sensitive clash with an existing display name.
    """
    from vaultkeeper.core.reserved import is_reserved_name_or_prefix

    name = name.rstrip(".")
    if name == "":
        return False, "You have not specified a File name"

    if "." not in name:
        name += IMAGE_EXTENSION

    if name.lower() == NWN_START_SCREEN_NAME.lower() or is_reserved_name_or_prefix(name):
        return False, f'"{name}" is a reserved name'

    if not name.lower().endswith(IMAGE_EXTENSION):
        return False, f'You must specify "{IMAGE_EXTENSION}" as the file extension name'

    if name == initial:  # case-sensitive: only a real change is allowed
        return False, f'"{name}" has not been changed'

    for other in existing:
        if name == other:  # case-sensitive clash on display name
            return False, f'"{name}" already exists'

    return True, name


#: Bundled app-data file listing NWN's own GUI TGAs to skip when adding from archives.
_DATA_DIR = Path(__file__).resolve().parent / "data"
_EXCLUSIONS_FILE = _DATA_DIR / "LoadscreenExclusions.txt"


def tga_file_exclusions() -> set[str]:
    """NWN GUI TGA names to skip when extracting archives (VB ``TgaFileExclusions``).

    Read from the bundled ``LoadscreenExclusions.txt`` (verbatim from the original
    app's install dir). These are NWN's own interface images (logos, load/save
    screens) that would otherwise be mistaken for user loadscreens. Returns a
    lower-cased set; matching is case-insensitive (VB ``CurrentCultureIgnoreCase``).
    """
    if not _EXCLUSIONS_FILE.is_file():
        return set()
    try:
        text = _EXCLUSIONS_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return {line.strip().lower() for line in text.splitlines() if line.strip()}


def collect_tga_from_folders(
    folders: Iterable[Path],
    *,
    extract: object = None,
    is_archive: object = None,
    exclusions: object = (),
) -> list[Path]:
    """Collect every ``.tga`` under ``folders``, extracting nested archives (VB ``ProcessFolders``).

    Walks each folder recursively (``EnumerateFiles(*, AllDirectories)``): loose
    ``.tga`` files are collected as-is; archive files are queued for extraction (via
    the injected ``extract(archive) -> dest_dir | None`` seam) and their extracted
    ``.tga`` files collected, minus any whose name is in ``exclusions`` (VB
    ``TgaFileExclusions``). Nested archives inside an extraction are queued in turn.
    ``is_archive(path) -> bool`` identifies archives (defaults to the core registry).
    """
    from vaultkeeper.core.archive import is_zip_extension

    if is_archive is None:
        def is_archive(path: Path) -> bool:  # noqa: ANN001
            return is_zip_extension(path.suffix)

    exclude = {str(name).lower() for name in exclusions}
    files: list[Path] = []
    extract_queue: list[Path] = []

    for folder in folders:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for entry in sorted(folder.rglob("*")):
            if not entry.is_file():
                continue
            if entry.suffix.lower() == IMAGE_EXTENSION:
                files.append(entry)
            elif is_archive(entry):
                extract_queue.append(entry)

    while extract_queue and extract is not None:
        batch = list(extract_queue)
        extract_queue.clear()
        for archive in batch:
            dest = extract(archive)
            if dest is None:
                continue
            for entry in sorted(Path(dest).rglob("*")):
                if not entry.is_file():
                    continue
                if entry.suffix.lower() == IMAGE_EXTENSION:
                    if entry.name.lower() not in exclude:
                        files.append(entry)
                elif is_archive(entry):
                    extract_queue.append(entry)

    return files


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
    prefixes: dict[str, bool] | None = None,
) -> list[LoadscreenImage]:
    """List the ``.tga`` images in ``image_folder``, Windows-sorted by name.

    The display name is the file name including the ``.tga`` extension (VB's
    ``FvImages`` combines the display name directly onto ``ImageFolder``). ``active``
    marks the currently-active image; ``excludes`` marks auto-excluded images;
    ``prefixes`` (from :func:`read_prefixes`) marks prefixed / enabled-prefixed
    images. All comparisons are case-insensitive, matching VB's ``Option Compare
    Text``.
    """
    if not image_folder.is_dir():
        return []

    exclude_set = {str(name).lower() for name in excludes}
    active_lower = active.lower()
    prefix_map = prefixes or {}

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
                prefixed=is_prefixed(name, prefix_map),
                filter_prefixed=is_filter_prefixed(name, prefix_map),
            )
        )

    entries.sort(key=cmp_to_key(lambda a, b: win_compare(a.name, b.name)))
    return entries
