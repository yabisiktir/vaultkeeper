"""Superseded downloads: the previous version of what was just fetched.

Downloading v1.2 of a mod over v1.1 leaves v1.1 in the mod's ``_Downloads``
folder for ever. Nothing removes it, and nothing has to — until the folder holds
four versions of a 400 MB module and building the installer picks up whichever
one the extractor reaches first.

Which files those are cannot be asked of the Vault: the project publishes what
it publishes now, and says nothing about what it used to. So it is worked out
from the names, and the two ways a mod is versioned are both handled:

* **a version suffix** — ``mymodule_1_1.7z`` and ``mymodule_1_2.7z`` share the
  stem ``mymodule``;
* **a date in the name** — ``mymodule_20250104.7z`` and ``mymodule_20260214.7z``
  are the same file with the date taken out.

Everything here returns *suggestions*, ticked or unticked, for someone to
confirm. A name-matching rule cannot know that two archives are versions of each
other rather than two halves of a set (``cep_3.1.4_-_part_1``), and deleting the
wrong one throws away a download that may no longer be available anywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import ARCHIVE_EXTENSIONS

#: Marks stripped from a name part before asking whether it is a version number
#: (VB ``FileVersionPrefixList``). Order matters: "ver" before "v", or "ver1"
#: becomes "er1" and stops looking like a version.
_VERSION_PREFIXES = ("ver", "v", "beta", "alpha", ".mod")

#: ``yyyymmdd`` with any of the three separators people use.
_DATE = tuple(
    re.compile(rf"[0-9]{{4}}{sep}(0[1-9]|1[0-2]){sep}(0[1-9]|[12][0-9]|3[01])")
    for sep in ("", "-", "_")
)

#: Folders inside a mod that hold kept copies, not current downloads.
_KEPT = (C.HISTORY_DIR, C.PUBLISHED_DIR)


@dataclass(frozen=True)
class OldDownload:
    """A file in ``_Downloads`` that a newer one appears to replace."""

    path: Path
    #: Whether it is ticked when the list is shown. Ticked means a version or
    #: date of the same name matched; unticked means it is merely an older file
    #: sitting beside the new ones, offered in case it is wanted gone.
    suggested: bool

    @property
    def name(self) -> str:
        return self.path.name


def version_stem(filename: str) -> str:
    """The name with its trailing version parts removed (VB ``GetPartialName``).

    ``mymodule_v1_2.7z`` → ``mymodule``. A name with no version, or one whose
    stem would be too short to be a safe prefix match, comes back whole — a
    two-character stem would match half the folder.
    """
    stem = Path(filename).stem
    for delimiter in ("_", "-"):
        parts = stem.split(delimiter)
        if len(parts) > 1:
            break
    else:
        return stem

    # Walk in from the end for as long as the parts look like version numbers.
    index = len(parts)
    while index > 0 and _is_version_part(parts[index - 1]):
        index -= 1
    if index == len(parts) or index == 0:
        return stem  # no version found, or the whole name is one

    partial = delimiter.join(parts[:index])
    if len(partial) < 4 and len(partial) < len(stem) / 2:
        return stem  # too little left to match on safely
    return partial


def _is_version_part(part: str) -> bool:
    """Whether one dot/underscore-separated part reads as a version number."""
    trimmed = part
    for prefix in _VERSION_PREFIXES:
        trimmed = re.sub(re.escape(prefix), "", trimmed, flags=re.IGNORECASE)
    trimmed = trimmed.replace(".", "")
    return bool(trimmed) and trimmed.isdigit()


def date_stem(filename: str) -> str:
    """The name with a ``yyyymmdd``-style date removed, or "" if it has none.

    A dated release is the other way mods are versioned, and the date is the
    only part that changes between two of them.
    """
    stem = Path(filename).stem
    for pattern in _DATE:
        match = pattern.search(stem)
        if match:
            return stem.replace(match.group(0), "").replace("_", "").replace("-", "")
    return ""


def _wanted_extensions(incoming: list[str]) -> set[str]:
    """Extensions worth looking at, given what is being downloaded.

    An archive being downloaded puts *every* archive extension in scope: a
    project that shipped ``.rar`` last year and ``.7z`` this year is the same
    project, and the older file is exactly what this is for.
    """
    extensions = {Path(name).suffix.lower() for name in incoming if name}
    if any(ext in ARCHIVE_EXTENSIONS for ext in extensions):
        extensions |= set(ARCHIVE_EXTENSIONS)
    return extensions


def superseded(existing: list[Path], incoming: list[str]) -> list[OldDownload]:
    """Files in ``existing`` that the ``incoming`` download appears to replace.

    ``existing`` is what the mod's download folder holds; ``incoming`` the file
    names about to be written. A file that is *itself* being re-downloaded is
    never offered — it is about to be overwritten, not superseded.
    """
    incoming_names = {name.lower() for name in incoming if name}
    if not incoming_names:
        return []  # nothing arrived, so nothing was replaced
    extensions = _wanted_extensions(incoming)
    stems = {version_stem(name).lower() for name in incoming if name}
    stems.discard("")
    dates = {date_stem(name).lower() for name in incoming if name}
    dates.discard("")

    found: list[OldDownload] = []
    for path in existing:
        if path.name.lower() in incoming_names:
            continue
        if any(part in _KEPT for part in path.parts):
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        matched = (date_stem(path.name).lower() in dates and bool(dates)) or any(
            path.name.lower().startswith(stem) for stem in stems
        )
        found.append(OldDownload(path, matched))
    return sorted(found, key=lambda old: (not old.suggested, old.name.lower()))
