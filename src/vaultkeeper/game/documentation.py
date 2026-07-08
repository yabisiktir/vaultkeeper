"""Documentation-file discovery for the Mod Documentation Organiser.

Headless port of the file-scanning heart of VB ``DocOrganiser`` (``DocOrganiser.vb``
+ ``.DocInfo.vb`` + ``.ProcessDocs.vb``). The VB tool builds two lists per mod:

* **Contents** — documentation files already sitting in the mod's *root* folder
  (``ModData.ModPath`` = ``ProfileMods\\<mod>``; VB scans ``CurrentMod.Info.FullName``
  top-level, non-recursive). These are the docs the user can already read.
* **Downloads** — documentation files under the mod's ``_Downloads`` folder,
  scanned recursively *including inside archives* (``ZipManager.Extract``). These
  are candidates the user may copy up into the Contents panel.

A file counts as documentation when its extension is one of ``TextFiles`` and its
name is not in ``ExcludeFiles`` (``DocOrganiser.vb``); ``nwcontinst.exe`` is always
ignored, and the Contents scan additionally skips reserved names (so the mod's own
``.Game Play Time.rtf`` — which *would* match ``.rtf`` — is not mistaken for a doc).

This module is the read-only *report* layer: it enumerates and describes the doc
files. The copy/organise action (unique-name qualifiers, CRC dedupe against the
Contents panel, version-number stripping, actually copying files) is deferred —
see ``DocInfo``/``BtCopy_Click`` in the VB and the handoff note.

The archive-extract path is injected via an ``ArchiveExtractor`` seam
(``core/archive.py``); pass ``extractor=None`` to scan loose files only.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import is_extractable

#: Documentation file extensions (VB ``DocOrganiser.TextFiles``, verbatim).
DOC_EXTENSIONS: frozenset[str] = frozenset(
    {".txt", ".rtf", ".pdf", ".doc", ".docx", ".docm", ".htm", ".html"}
)

#: Files never processed at all (VB ``IgnoreFiles``).
IGNORE_NAMES: frozenset[str] = frozenset({"nwcontinst.exe"})

#: Doc-extension files still excluded from the lists (VB ``ExcludeFiles``).
EXCLUDE_NAMES: frozenset[str] = frozenset({"nwcontinst.exe", "manifest.txt"})

#: Reserved file names skipped by the Contents scan (VB ``Paths.IsReservedNameOrPrefix``
#: — the only reserved *file* that carries a doc extension is the play-time RTF).
_RESERVED_FILE_NAMES: frozenset[str] = frozenset({C.PLAY_TIME_FILE.lower()})


def is_doc_file(name: str) -> bool:
    """True if ``name`` is a documentation file (VB ``GetDocFile`` predicate).

    Extension must be in :data:`DOC_EXTENSIONS` and the (case-insensitive) name
    must not be in :data:`EXCLUDE_NAMES`.
    """
    lower = name.lower()
    return Path(lower).suffix in DOC_EXTENSIONS and lower not in EXCLUDE_NAMES


@dataclass(frozen=True)
class DocEntry:
    """A documentation file found in a mod (one row of the organiser report)."""

    mod: str
    file_name: str
    #: ``"Contents"`` (in the mod root) or ``"Downloads"`` (under ``_Downloads``).
    source: str
    #: Parent folder relative to the mod root, POSIX-style (``""`` at the root).
    folder: str
    size: int
    #: Absolute path on disk. For files pulled out of an archive this points into
    #: a temporary directory that is removed after the scan (ephemeral — name/size
    #: are captured, opening extracted docs is part of the deferred copy action).
    full_path: Path


def _rel_folder(path: Path, root: Path) -> str:
    """POSIX relative parent of ``path`` within ``root`` (``""`` when at root)."""
    rel = path.parent.relative_to(root)
    return "" if rel == Path(".") else rel.as_posix()


def _scan_contents(mod_name: str, mod_folder: Path) -> list[DocEntry]:
    """Docs already in the mod root folder (VB ContentsDocs, non-recursive)."""
    entries: list[DocEntry] = []
    for info in sorted(mod_folder.iterdir()):
        if not info.is_file():
            continue
        name = info.name
        lower = name.lower()
        if lower in IGNORE_NAMES or lower in _RESERVED_FILE_NAMES:
            continue
        if is_doc_file(name):
            entries.append(
                DocEntry(
                    mod=mod_name,
                    file_name=name,
                    source="Contents",
                    folder="",
                    size=info.stat().st_size,
                    full_path=info,
                )
            )
    return entries


def _scan_download_tree(
    mod_name: str, root: Path, tree: Path, folder_prefix: str
) -> tuple[list[DocEntry], list[Path]]:
    """Recursively collect docs (and extractable archives) under ``tree``.

    ``folder_prefix`` is prepended to the reported relative folder so files pulled
    from an archive keep a readable location. Returns ``(doc entries, archives)``.
    """
    entries: list[DocEntry] = []
    archives: list[Path] = []
    for info in sorted(p for p in tree.rglob("*") if p.is_file()):
        name = info.name
        if name.lower() in IGNORE_NAMES:
            continue
        if is_doc_file(name):
            folder = _rel_folder(info, root)
            if folder_prefix:
                folder = f"{folder_prefix}/{folder}" if folder else folder_prefix
            entries.append(
                DocEntry(
                    mod=mod_name,
                    file_name=name,
                    source="Downloads",
                    folder=folder,
                    size=info.stat().st_size,
                    full_path=info,
                )
            )
        elif is_extractable(info.suffix):
            archives.append(info)
    return entries, archives


def scan_mod_docs(
    mod_name: str, mod_folder: Path, *, extractor=None
) -> list[DocEntry]:
    """All documentation files for one mod (VB ``BgProcessDocs_DoWork`` scan).

    Scans the mod root (Contents) plus ``_Downloads`` recursively. When an
    ``extractor`` (``core.archive.ArchiveExtractor``) is supplied, archives found
    in ``_Downloads`` are extracted to a temporary folder and their loose docs are
    included too; without one, only loose files are reported (nested archives are
    not recursed — a bounded first version).
    """
    if not mod_folder.is_dir():
        return []

    entries = _scan_contents(mod_name, mod_folder)

    downloads = mod_folder / C.DOWNLOADS_DIR
    if downloads.is_dir():
        loose, archives = _scan_download_tree(
            mod_name, mod_folder, downloads, folder_prefix=""
        )
        entries.extend(loose)
        if extractor is not None and getattr(extractor, "available", False):
            entries.extend(
                _scan_archives(mod_name, mod_folder, archives, extractor)
            )

    return entries


def _scan_archives(
    mod_name: str, mod_folder: Path, archives: list[Path], extractor
) -> list[DocEntry]:
    """Extract each archive to a temp dir and collect its loose docs."""
    entries: list[DocEntry] = []
    for archive in archives:
        with tempfile.TemporaryDirectory(prefix="vk_docorg_") as tmp:
            result = extractor.extract(archive, Path(tmp))
            if not result.ok:
                continue
            rel_archive = archive.relative_to(mod_folder).as_posix()
            found, _ = _scan_download_tree(
                mod_name, Path(tmp), Path(tmp), folder_prefix=f"{rel_archive}!"
            )
            entries.extend(found)
    return entries
