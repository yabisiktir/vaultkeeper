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

Beyond enumeration this module ports the VB ``DocInfo``/``ProcessDocs`` naming and
dedup logic that drives the copy action:

* **Qualifier + ``DocName``** (``DocInfo``): a downloaded doc's target name is the
  qualifier (the mod name for loose files, or the archive/zip folder name for
  extracted files) plus a title-cased, optionally version-stripped file name —
  unless the file name already starts with the qualifier.
* **CRC dedup** (``ProcessDocs``): a downloaded doc whose CRC-32 matches a doc
  already in Contents is marked *not to copy* (``copy=False``) and linked to the
  match (``name_match``); the Contents doc is linked back.
* **Unique numbering**: downloaded docs that would collide on ``DocName`` get a
  trailing ``" 1"``/``" 2"`` etc.

The LazWorks string helpers ``FilenameOnly``/``ToTitleCaseSentence("_")`` /
``GetExtension`` and ``IsNumeric`` are **not** in the source tree, so they are
reconstructed from usage (drop the folder+extension; ``_``→space + title-case
word initials; ``IsNumeric`` ≈ parses as a number) — matching the reconstruction
in ``game/wizard.py``. Note where exact casing / lenient-numeric parsing could
diverge.

The archive-extract path is injected via an ``ArchiveExtractor`` seam
(``core/archive.py``); pass ``extractor=None`` to scan loose files only. Archive
docs are described and CRC-matched for the report, but the *copy* action currently
handles only loose ``_Downloads`` files (their source survives the scan); copying
docs back out of archives would need re-extraction and is deferred.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import is_extractable
from vaultkeeper.core.crc import crc32_file

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


# -- LazWorks string helpers (reconstructed from usage) -------------------- #


def _filename_only(name: str) -> str:
    """Stem of the last path component (VB ``FilenameOnly``; ``\\`` or ``/`` paths)."""
    return PurePosixPath(name.replace("\\", "/")).stem


def _get_extension(name: str) -> str:
    """Extension including the dot (VB ``GetExtension``; ``""`` when none)."""
    return PurePosixPath(name.replace("\\", "/")).suffix


def _to_title_case_sentence(text: str, sep: str = "_") -> str:
    """VB ``ToTitleCaseSentence("_")`` — split on ``sep``, title-case each word.

    Reconstructed (LazWorks helper absent): replace the separator with a space and
    upper-case each word's initial, leaving the remainder as-is (matches
    ``game/wizard._default_display``). Exact casing of all-caps words is unverified.
    """
    words = text.replace(sep, " ").split()
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _is_numeric(value: str) -> bool:
    """Approximation of VB ``IsNumeric`` — does ``value`` parse as a number?

    VB's ``IsNumeric`` is more lenient (hex ``&H``, currency, etc.); for the version
    tokens this is used on (``2``, ``2.0``, ``3``) a plain float parse suffices.
    """
    value = value.strip()
    if value == "":
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def _is_version_number(value: str) -> bool:
    """VB ``DocInfo.IsVersionNumber`` — numeric, or ``v``-prefixed numeric (``v2``)."""
    if _is_numeric(value):
        return True
    return len(value) >= 1 and value[:1].lower() == "v" and _is_numeric(value[1:])


def _remove_version_text(value: str) -> str:
    """VB ``DocInfo.RemoveVersionText`` — strip trailing version-number words.

    Repeatedly drops the final space-delimited token while it looks like a version
    number. Guards the no-space case (VB would raise on a purely-version value; here
    it is simply left unchanged).
    """
    while True:
        last_space = value.rfind(" ")
        if last_space < 0:
            break
        if _is_version_number(value[last_space + 1 :]):
            value = value[:last_space]
        else:
            break
    return value


# -- Doc entry ------------------------------------------------------------- #


@dataclass
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
    #: are captured, opening/copying extracted docs is part of the deferred path).
    full_path: Path
    #: Qualified target name for the copy action (VB ``DocInfo.DocName``). For a
    #: Contents doc this is just the file name.
    doc_name: str = ""
    #: Whether the doc should be copied (VB ``DocInfo.Copy``); ``False`` once a CRC
    #: match with an existing Contents doc is found.
    copy: bool = True
    #: Path of the matching doc when CRC-deduped, else ``""`` (VB ``NameMatch``).
    name_match: str = ""
    #: CRC-32 of the file (VB ``DocInfo.Checksum``).
    checksum: int = 0
    #: Qualifier used to build ``doc_name`` (VB ``DocInfo.Qualifier``).
    qualifier: str = ""
    #: Qualifier with version text removed, when different (VB ``VersionlessQualifier``).
    versionless_qualifier: str = ""
    #: True when the doc was pulled out of a ``_Downloads`` archive.
    from_archive: bool = False


#: Separates a doc's ``_Downloads`` archive path from its path *inside* that archive
#: in :attr:`DocEntry.folder` (e.g. ``pack.zip!docs``); used to recover the source
#: for copy-from-archive.
ARCHIVE_SEPARATOR = "!"


def archive_source(entry: DocEntry) -> tuple[str, str] | None:
    """(mod-relative archive path, inner file path) for an archive doc, else ``None``.

    Recovers, from a ``from_archive`` entry's :attr:`~DocEntry.folder`
    (``<archive>!<inner-parent>``) plus its file name, the info a copy needs to
    re-extract that one doc: which ``_Downloads`` archive it came from and its path
    within it.
    """
    if not entry.from_archive or ARCHIVE_SEPARATOR not in entry.folder:
        return None
    rel_archive, _, inner_parent = entry.folder.partition(ARCHIVE_SEPARATOR)
    inner = f"{inner_parent}/{entry.file_name}" if inner_parent else entry.file_name
    return rel_archive, inner


def _rel_folder(path: Path, root: Path) -> str:
    """POSIX relative parent of ``path`` within ``root`` (``""`` when at root)."""
    rel = path.parent.relative_to(root)
    return "" if rel == Path(".") else rel.as_posix()


def _checksum(path: Path) -> int:
    """CRC-32 of ``path``; 0 if it cannot be read (VB flags rather than crashes)."""
    try:
        return crc32_file(path)
    except OSError:
        return 0


def _doc_name_for(
    file_name: str, qualifier: str, from_archive: bool, remove_version: bool
) -> tuple[str, str, str]:
    """Build (doc_name, qualifier, versionless_qualifier) — VB ``DocInfo`` (qualified).

    Ports ``DocInfo.New(info, qualified:=True)``: the display file name is the stem
    title-cased (optionally version-stripped) plus the original extension; the
    qualifier is prepended unless the file name already starts with it.
    """
    ext = _get_extension(file_name)
    disp = _to_title_case_sentence(_filename_only(file_name), "_")
    if remove_version:
        disp = _remove_version_text(disp)
    disp += ext

    if not from_archive:
        # Loose file: qualifier is the mod display name (passed in), always prefixed.
        return f"{qualifier} {disp}", qualifier, ""

    # Extracted file: qualifier is the archive/zip folder name, title-cased.
    versionless = ""
    new_qualifier = _remove_version_text(qualifier)
    if new_qualifier != qualifier:
        versionless = new_qualifier
    if remove_version and versionless != "":
        qualifier = versionless

    if disp.lower().startswith(qualifier.lower()):
        return disp, qualifier, versionless
    return f"{qualifier} {disp}", qualifier, versionless


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
            # VB DocInfo(qualified:=False): no name change, DocName = file name.
            entries.append(
                DocEntry(
                    mod=mod_name,
                    file_name=name,
                    source="Contents",
                    folder="",
                    size=info.stat().st_size,
                    full_path=info,
                    doc_name=name,
                    checksum=_checksum(info),
                    qualifier=mod_name,
                )
            )
    return entries


def _scan_download_tree(
    mod_name: str,
    root: Path,
    tree: Path,
    *,
    folder_prefix: str,
    qualifier: str,
    from_archive: bool,
    remove_version: bool,
) -> tuple[list[DocEntry], list[Path]]:
    """Recursively collect docs (and extractable archives) under ``tree``.

    ``folder_prefix`` is prepended to the reported relative folder so files pulled
    from an archive keep a readable location. ``qualifier`` seeds the ``DocName``
    (mod name for loose files, archive/zip folder name for extracted files).
    Returns ``(doc entries, archives)``.
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
            doc_name, qual, versionless = _doc_name_for(
                name, qualifier, from_archive, remove_version
            )
            entries.append(
                DocEntry(
                    mod=mod_name,
                    file_name=name,
                    source="Downloads",
                    folder=folder,
                    size=info.stat().st_size,
                    full_path=info,
                    doc_name=doc_name,
                    checksum=_checksum(info),
                    qualifier=qual,
                    versionless_qualifier=versionless,
                    from_archive=from_archive,
                )
            )
        elif is_extractable(info.suffix):
            archives.append(info)
    return entries, archives


def _process_docs(contents: list[DocEntry], downloads: list[DocEntry]) -> None:
    """VB ``BgProcessDocs_DoWork`` post-passes: CRC dedup + unique numbering.

    Mutates the entries in place. A downloaded doc whose CRC matches an existing
    Contents doc is marked ``copy=False`` and linked both ways; remaining duplicate
    ``DocName`` values are made unique with a trailing number.
    """
    # CRC dedup — link a download to the first Contents doc with the same checksum.
    for dl in downloads:
        for ct in contents:
            if dl.checksum == ct.checksum:
                dl.doc_name = ct.doc_name
                dl.copy = False
                dl.name_match = str(ct.full_path)
                ct.name_match = str(dl.full_path)
                break

    # Ensure DocNames are unique by appending a numeric suffix (VB Option Compare
    # Text → case-insensitive grouping).
    for dl in downloads:
        target = dl.doc_name.lower()
        dupes = [d for d in downloads if d.doc_name.lower() == target]
        if len(dupes) > 1:
            for number, dup in enumerate(dupes, start=1):
                stem = _filename_only(dup.doc_name)
                ext = _get_extension(dup.doc_name)
                dup.doc_name = f"{stem} {number}{ext}"


def scan_mod_docs(
    mod_name: str, mod_folder: Path, *, extractor=None, remove_version: bool = False
) -> list[DocEntry]:
    """All documentation files for one mod (VB ``BgProcessDocs_DoWork`` scan).

    Scans the mod root (Contents) plus ``_Downloads`` recursively, computing each
    doc's qualified ``DocName``, CRC-32, and copy/match state (VB ``DocInfo`` /
    ``ProcessDocs``). When an ``extractor`` (``core.archive.ArchiveExtractor``) is
    supplied, archives found in ``_Downloads`` are extracted to a temporary folder
    and their loose docs are included too; without one, only loose files are
    reported (nested archives are not recursed — a bounded first version).

    ``remove_version`` mirrors the VB *Version* toggle (default off): strip trailing
    version numbers from qualifiers/names when building ``DocName``.
    """
    if not mod_folder.is_dir():
        return []

    contents = _scan_contents(mod_name, mod_folder)
    downloads: list[DocEntry] = []

    dl_folder = mod_folder / C.DOWNLOADS_DIR
    if dl_folder.is_dir():
        loose, archives = _scan_download_tree(
            mod_name,
            mod_folder,
            dl_folder,
            folder_prefix="",
            qualifier=mod_name,
            from_archive=False,
            remove_version=remove_version,
        )
        downloads.extend(loose)
        if extractor is not None and getattr(extractor, "available", False):
            downloads.extend(
                _scan_archives(
                    mod_name, mod_folder, archives, extractor, remove_version
                )
            )

    _process_docs(contents, downloads)
    return contents + downloads


def _doc_members(archive: Path, extractor) -> list[str] | None:
    """The archive's documentation members, or ``None`` if it cannot be listed.

    ``None`` and ``[]`` mean different things and the caller relies on it: an
    empty list is "listed, and there is no documentation in here", while ``None``
    is "could not look", which falls back to extracting everything.
    """
    entries = _list_entries(archive, extractor)
    if entries is None:
        return None
    return [e["path"] for e in entries]


def _list_entries(archive: Path, extractor) -> list[dict] | None:
    """Documentation members with the metadata the scan needs, straight from the index.

    A 7-Zip listing carries each member's path, size **and CRC**, which is
    everything a report row needs — so an archive's docs can be described
    without unpacking a byte. That matters because extraction is not merely
    slower: 7z archives are usually *solid*, so pulling one 112-byte readme out
    of CEP's 1.2 GB part still decompresses the block, and measured at 8.7
    seconds against 0.01 to list it.
    """
    lister = getattr(extractor, "list_entries", None)
    if not callable(lister):
        return None
    entries = lister(archive)
    if entries is None:
        return None
    return [e for e in entries if is_doc_file(PurePosixPath(e["path"]).name)]


def _scan_archives(
    mod_name: str,
    mod_folder: Path,
    archives: list[Path],
    extractor,
    remove_version: bool,
) -> list[DocEntry]:
    """Collect the docs inside each archive, without unpacking it.

    A 7-Zip listing carries each member's path, size and CRC, which is the whole
    of what a report row needs — so the archives are described from their index.
    This used to extract every archive in full: on a store holding CEP that took
    twenty seconds and wrote several gigabytes of temporary files to find one
    readme, because CEP's two parts expand to over five gigabytes between them.

    Extraction is not merely slower, either. 7z archives are usually *solid*, so
    pulling a single 112-byte readme out of the 1.2 GB part still decompresses
    the block — measured at 8.7 seconds, against 0.01 to list it.

    An archive that cannot be listed still falls back to extraction, so an odd
    format or an older backend reports its docs rather than none.
    """
    entries: list[DocEntry] = []
    for archive in archives:
        rel_archive = archive.relative_to(mod_folder).as_posix()
        # VB qualifier for extracted docs = the zip folder name, title-cased.
        qualifier = _to_title_case_sentence(_filename_only(archive.name), "_")
        listed = _list_entries(archive, extractor)

        if listed is not None:
            entries.extend(
                _entry_from_listing(
                    mod_name, archive, rel_archive, qualifier, member, remove_version
                )
                for member in listed
            )
            continue

        # Could not be listed: unpack and scan as before.
        with tempfile.TemporaryDirectory(prefix="vk_docorg_") as tmp:
            result = extractor.extract(archive, Path(tmp))
            if not result.ok:
                continue
            found, _ = _scan_download_tree(
                mod_name,
                Path(tmp),
                Path(tmp),
                folder_prefix=f"{rel_archive}{ARCHIVE_SEPARATOR}",
                qualifier=qualifier,
                from_archive=True,
                remove_version=remove_version,
            )
            entries.extend(found)
    return entries


def _entry_from_listing(
    mod_name: str,
    archive: Path,
    rel_archive: str,
    qualifier: str,
    member: dict,
    remove_version: bool,
) -> DocEntry:
    """One report row built from an archive's index rather than its contents."""
    inner = PurePosixPath(member["path"])
    folder = f"{rel_archive}{ARCHIVE_SEPARATOR}{inner.parent.as_posix()}"
    doc_name, _, _ = _doc_name_for(inner.name, qualifier, True, remove_version)
    return DocEntry(
        mod=mod_name,
        file_name=inner.name,
        source="Downloads",
        folder=folder.rstrip("."),
        size=member.get("size", 0),
        # The file is not on disk. ``archive!inner`` is the same shape the copy
        # path already understands (see ``archive_source``), so it re-extracts
        # this one member when the user actually asks for it.
        full_path=archive.parent / f"{archive.name}{ARCHIVE_SEPARATOR}{inner}",
        doc_name=doc_name,
        checksum=member.get("crc", 0),
        from_archive=True,
    )
