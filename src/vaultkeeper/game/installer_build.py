"""Create-Installer payload builder (VB ``CreateInstaller`` worker pipeline).

This is the correctness-critical code that decides **which files get copied into a
mod's ``.Mod Installer`` payload, and into which game folder** — the thing a real
installer install then applies to the user's game. It is a faithful headless port
of the ``BgScanner → BgExtractor → BgAnalyser`` half of ``CreateInstaller.vb``,
centred on ``Analyse`` (@1347) and the ``CopyList`` structure it builds, plus the
plan the ``CopyToInstallers`` (@1632) step consumes.

Pipeline (headless, Qt-free):

* **Scan** (``ScanFolders`` / ``ScanFile``): walk the mod folder top-down. Loose
  archives are extracted via the injected :class:`ArchiveExtractor` seam and their
  contents re-scanned (VB ``BgExtractor``); every other supported file is fed to
  ``Analyse``. Hidden/system files, excluded ERF folders and excluded folders are
  skipped exactly as VB does; ``_Downloads`` / ``_Published`` are traversed (so
  downloaded archives are extracted) while ``.Mod Installer`` (the copy *target*)
  is not.
* **Analyse** (``Analyse``): build ``CopyList[mod][targetFolder][filename] =
  CopyInfo``, applying the Mapper eligibility ladder (``GetMappedFolder(fi, True)``),
  the secondary-folder resolution (``GetSecondaryFolder`` / ``GetPrimaryFolder``),
  the duplicate tie-break by ``LastWriteTime``, the placeholder-``.mod``-size guard
  (``PlaceholderModSize`` / ``Mapper.C.ModFile``), and the excluded-file / demo-mod
  skips (``Map.IsExcludedFile`` / ``Map.IsDemoMod``).
* **Plan**: flatten ``CopyList`` into a list of :class:`CopyPlanItem` — one
  ``(source, target-folder, filename)`` per file to copy under
  ``.Mod Installer/<folder>/<filename>``. The plan is a pure data structure; the
  actual file copy is a separate controller step so the plan is unit-testable
  without touching disk state.

**Bounded — deferred with notes** (mirrors how DocOrganiser did loose-file copy
first): the ``BgConverter`` BIK→WBM conversion (needs ffmpeg) is not performed —
with ``convert_bik=False`` (the port default) ``.bik`` files fall through to be
analysed/copied as-is, exactly as VB does when ``ConvertBikFiles`` is off; ``True``
(conversion) is deferred. ``ProcessPatchFiles`` (reassigning ``nwnpatch.ini`` haks
to the ``patch`` folder) and the ``.Installer Wizard`` RunWizard modal flow
(select-one/select-many file exclusion) are deferred — the wizard's *ignore list*
would only ever *remove* files from the plan, so omitting it is a safe over-set.
Self-extracting ``.exe`` archives are treated as non-extractable (VB probes them
with 7-Zip; deferred), so they are simply skipped.
"""

from __future__ import annotations

import tempfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import ArchiveExtractor, is_extractable
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.game.wizard import WIZARD_FILE

#: A mod folder smaller than this is assumed to be a placeholder (VB
#: ``PlaceholderModSize`` = 3 MiB); used to keep a larger older ``.mod`` over a
#: newer but tiny placeholder duplicate.
PLACEHOLDER_MOD_SIZE = 3 * 1024 * 1024


@dataclass
class SourceFile:
    """A candidate source file for the installer (VB ``FileInfo`` view).

    Carries the full :attr:`path` (used for the Mapper's folder resolution, which
    inspects the parent/grandparent directory names) plus the :attr:`size` and
    :attr:`mtime` the Analyse duplicate tie-break needs. Constructing one directly
    (with a synthetic path) lets the Analyse rules be unit-tested off-disk.
    """

    path: Path
    size: int
    mtime: float

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix

    @classmethod
    def from_path(cls, path: Path) -> SourceFile:
        stat = path.stat()
        return cls(path=path, size=stat.st_size, mtime=stat.st_mtime)


@dataclass
class CopyInfo:
    """One planned copy: the winning source for a ``(mod, folder, filename)`` slot.

    VB ``CopyInfo`` also stores ``InstallerPath``; here that is per-mod constant
    (every file of a mod shares the same ``.Mod Installer`` target), so it is
    applied when the plan is built rather than duplicated on every entry.
    """

    source: SourceFile


#: ``CopyList[modname][targetFolder][filename] -> CopyInfo`` (VB nested dict).
CopyList = dict[str, dict[str, dict[str, CopyInfo]]]


@dataclass
class CopyPlanItem:
    """One file to copy into the installer payload."""

    source: Path
    folder: str
    filename: str

    @property
    def target_rel(self) -> str:
        """Payload-relative destination ``<folder>/<filename>``."""
        return f"{self.folder}/{self.filename}"


@dataclass
class InstallerPlan:
    """The result of analysing a mod: its ``CopyList`` and a flat copy plan."""

    mod_name: str
    copy_list: CopyList = field(default_factory=dict)
    items: list[CopyPlanItem] = field(default_factory=list)
    #: Files skipped by MapExcludes / demo-mod rules (VB ``MapExcludesList``).
    excluded: list[str] = field(default_factory=list)
    files_scanned: int = 0
    archives_extracted: int = 0


# --------------------------------------------------------------------------- #
# Analyse (VB CreateInstaller.Analyse @1347)
# --------------------------------------------------------------------------- #


class _Analyser:
    """Builds the ``CopyList`` one file at a time (faithful port of ``Analyse``)."""

    def __init__(self, mapper: Mapper, *, paste_active: bool = False) -> None:
        self._map = mapper
        self._paste_active = paste_active
        self.copy_list: CopyList = {}
        self.excluded: list[str] = []

    def _is_excluded_file(self, sf: SourceFile) -> bool:
        """VB ``Map.IsExcludedFile(fi)`` — tests both the name and ``dir\\name``."""
        name = sf.name
        parent = sf.path.parent.name
        return self._map.is_excluded_file(name) or self._map.is_excluded_file(
            f"{parent}\\{name}"
        )

    def analyse(self, modname: str, sf: SourceFile) -> None:
        """Decide whether/where ``sf`` is copied for ``modname`` (VB ``Analyse``)."""
        name = sf.name

        # Ignore excluded files and demo mods (PasteActive is always False here).
        if not self._paste_active and (
            self._is_excluded_file(sf) or self._map.is_demo_mod(name)
        ):
            self.excluded.append(name)
            return

        # Ignore extensions that are not supported (erf check on, as VB does).
        target = self._map.get_mapped_folder(sf.path, erf_check=True)
        if target == "":
            return

        mod = self.copy_list.setdefault(modname, {})
        folder = mod.setdefault(target, {})
        ci = CopyInfo(source=sf)
        secondary = self._map.get_secondary_folder(sf.extension)

        # -- No secondary folder defined ---------------------------------- #
        if secondary == "":
            existing = folder.get(name)
            if existing is None:  # noqa: SIM114 - kept distinct to mirror VB Analyse
                folder[name] = ci
            elif sf.mtime > existing.source.mtime and (
                # Retain the older version if the new one is a placeholder mod.
                sf.extension.lower() != C.EXT_MOD
                or sf.size > PLACEHOLDER_MOD_SIZE
                or sf.size > existing.source.size
            ):
                folder[name] = ci
            return

        # -- The source directory overrode the default mapping ------------ #
        if target != secondary:
            sec = mod.get(secondary)
            if sec is None or name not in sec:
                existing = folder.get(name)
                if existing is None or sf.mtime > existing.source.mtime:
                    folder[name] = ci
            elif sf.mtime > sec[name].source.mtime:
                sec[name] = ci
            return

        # -- target == secondary: reconcile with any primary-folder copy -- #
        primary = self._map.get_primary_folder(sf.extension)
        prim = self.copy_list[modname].get(primary)
        sec = self.copy_list[modname].get(secondary)
        if prim is not None and name in prim and sec is not None and name in sec:
            if sf.mtime > prim[name].source.mtime:
                # The existing primary file is not the latest version.
                sec[name] = ci
            else:
                # The existing primary file is newer than the secondary file.
                sec[name].source = prim[name].source
            # Remove the entry for the primary file.
            del prim[name]
        else:
            existing = folder.get(name)
            if existing is None or sf.mtime > existing.source.mtime:
                folder[name] = ci


# --------------------------------------------------------------------------- #
# Scan (VB CreateInstaller.ScanFolders / ScanFile + BgExtractor)
# --------------------------------------------------------------------------- #


def _is_hidden(name: str) -> bool:
    """Cross-platform proxy for VB's Hidden/System attribute check."""
    return name.startswith(".")


def build_copy_plan(
    mod_name: str,
    mod_folder: Path,
    *,
    mapper: Mapper,
    extractor: ArchiveExtractor | None = None,
    extract_root: Path | None = None,
    convert_bik: bool = False,
) -> InstallerPlan:
    """Scan ``mod_folder`` and return the installer :class:`InstallerPlan`.

    Loose archives are extracted with ``extractor`` (into ``extract_root`` — a
    fresh temp dir if omitted) and their contents re-scanned; the plan's source
    paths therefore point either under ``mod_folder`` or under ``extract_root``, so
    the caller must keep ``extract_root`` alive until the copy step runs. Pass
    ``extractor=None`` to scan loose files only (archives are then ignored).
    """
    plan = InstallerPlan(mod_name=mod_name)
    analyser = _Analyser(mapper)

    if extract_root is None:
        extract_root = Path(tempfile.mkdtemp(prefix="vk-installer-"))

    # Queue of (modname, directory) to scan — extracted dirs are added as found.
    scan_queue: deque[Path] = deque([mod_folder])
    extract_counter = 0

    while scan_queue:
        folder = scan_queue.popleft()
        archives = _scan_folder(folder, mapper, analyser, plan, convert_bik=convert_bik)
        for archive in archives:
            if extractor is None or not is_extractable(archive.suffix):
                continue
            dest = extract_root / f"x{extract_counter:04d}"
            extract_counter += 1
            result = extractor.extract(archive, dest)
            if result.ok:
                plan.archives_extracted += 1
                scan_queue.append(dest)

    _build_items(analyser.copy_list, plan)
    plan.excluded = analyser.excluded
    return plan


def _scan_folder(
    folder: Path,
    mapper: Mapper,
    analyser: _Analyser,
    plan: InstallerPlan,
    *,
    convert_bik: bool,
) -> list[Path]:
    """Scan one directory (VB ``ScanFolders``); return archives found for extraction."""
    if not folder.is_dir():
        return []

    archives: list[Path] = []
    erf_excluded = mapper.is_excluded_erf_folder(folder.name)

    for fi in sorted(p for p in folder.iterdir() if p.is_file()):
        name = fi.name
        if _is_hidden(name):
            continue
        # A whole excluded ERF folder suppresses every file directly inside it.
        if erf_excluded:
            continue

        if is_extractable(fi.suffix):
            # Compressed file → extract queue, unless MapExcludes bars it (VB ScanFile).
            if not (
                mapper.is_excluded_file(name)
                or mapper.is_excluded_file(f"{folder.name}\\{name}")
            ):
                archives.append(fi)
            continue

        # BIK conversion is deferred; with convert_bik off, .bik falls through to
        # be analysed as-is (faithful to VB when ConvertBikFiles is False).
        if fi.suffix.lower() == ".bik" and convert_bik:
            continue
        # The downloaded-wizard copy path is part of the deferred wizard flow.
        if name == WIZARD_FILE:
            continue

        analyser.analyse(plan.mod_name, SourceFile.from_path(fi))
        plan.files_scanned += 1

    # Recurse into sub-folders, skipping excluded ones (VB ContainsExcludedFolder).
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        if mapper.contains_excluded_folder(str(sub)):
            continue
        archives.extend(
            _scan_folder(sub, mapper, analyser, plan, convert_bik=convert_bik)
        )

    return archives


def _build_items(copy_list: CopyList, plan: InstallerPlan) -> None:
    """Flatten ``CopyList`` into ``plan.items`` (the CopyToInstallers item list)."""
    for _modname, folders in copy_list.items():
        for target, files in folders.items():
            for filename, ci in files.items():
                plan.items.append(
                    CopyPlanItem(source=ci.source.path, folder=target, filename=filename)
                )
    plan.copy_list = copy_list


def target_folder_for(mapper: Mapper, path: str | PurePath) -> str:
    """Convenience: the folder a single file would map to (Analyse's first gate)."""
    return mapper.get_mapped_folder(path, erf_check=True)
