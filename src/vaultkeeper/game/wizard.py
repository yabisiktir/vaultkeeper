"""Mod Installer Wizard definitions (VB ``WizardInfo`` / ``WizardBuilder``).

A *wizard* is a small text file (``.Installer Wizard.nitwiz``) stored in a mod's
root folder that customises how the mod's installer behaves: an optional title,
whether archives must be extracted first, a **SelectOne** group (mutually-exclusive
"choices"), a **SelectMany** group (optional "preferences" with default checked
state), and an **InstallerExcludes** list (files the Create-Installer step skips).

This module is the headless read/write model. It parses that file into a
:class:`WizardInfo` (faithful port of ``WizardInfo.Load`` / ``GetItemInfo`` /
``AddSelectOne`` / ``AddSelectMany``), serialises it back with
:func:`convert_to_text` (``ConvertToText``), persists/removes it with
:func:`save_wizard` / :func:`delete_wizard` (``Save`` / ``Delete``), and validates
its statements against the mod's real files with :func:`scan_mod_files` /
:func:`validate` (``ScanFiles`` / ``Validate``). ``Option Compare Text`` makes
keyword matching and file-name comparisons case-insensitive.

Bounded: :func:`scan_mod_files` scans loose mod files (and lists archives by name,
matching VB's initial ``ScanFiles`` pass), but *does not* extract archives to
enumerate their contents — the recursive ``ProcessArchive`` path (validating files
referenced *inside* archives) needs the extract seam and is deferred, as is the
add/remove editing UI. Entries that point inside an un-extracted archive therefore
validate as missing; note this before wiring the extract pass.

The LazWorks string helpers ``FilenameOnly``/``ToSentence("_")``/``ToTitleCase`` used
to derive a default display name are not present in the source tree; their behaviour
is reconstructed from usage (drop the folder+extension, ``_``→space, title-case).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path, PurePosixPath

from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import is_zip_extension

#: Wizard definition file name (VB ``Paths.C.WizardFile`` = ``.Installer Wizard`` +
#: ``.nitwiz``), stored in the mod root folder.
WIZARD_FILE = ".Installer Wizard.nitwiz"

# Wizard rule keywords (VB ``WizardInfo.C``).
_WIZARD_TITLE = "WizardTitle"
_EXTRACT_ARCHIVES = "ExtractArchives"
_SELECT_ONE = "SelectOne"
_SELECT_MANY = "SelectMany"
_INSTALLER_EXCLUDES = "InstallerExcludes"
_END_SELECT_ONE = "End " + _SELECT_ONE
_END_SELECT_MANY = "End " + _SELECT_MANY
_END_INSTALLER_EXCLUDES = "End " + _INSTALLER_EXCLUDES
_NAME_SEPARATOR = ">"


@dataclass
class WizardPreference:
    """One SelectMany item: a relative path, display name and default state."""

    key: str
    display: str
    checked: bool


@dataclass
class WizardInfo:
    """Parsed wizard definition (VB ``WizardInfo``)."""

    mod_name: str = ""
    #: Raw title as stored; use :attr:`title` for the display value.
    title_value: str = ""
    extract_archives: bool = False
    select_one_text_value: str = ""
    select_many_text_value: str = ""
    #: SelectOne items — relative path → display name (case-insensitive keys).
    select_one: dict[str, str] = field(default_factory=dict)
    #: SelectMany items in file order.
    select_many: list[WizardPreference] = field(default_factory=list)
    #: Files excluded from the Create-Installer step.
    installer_excludes: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        """Windows-title text, defaulting from the mod name (VB ``Title`` getter)."""
        if self.title_value:
            return self.title_value
        if self.mod_name:
            return f"{self.mod_name} Installer Wizard"
        return "Mod Installer Wizard"

    @property
    def select_one_text(self) -> str:
        """SelectOne instruction text (VB default when blank)."""
        return self.select_one_text_value or "Choose which file you want to use."

    @property
    def select_many_text(self) -> str:
        """SelectMany instruction text (VB default when blank)."""
        return (
            self.select_many_text_value
            or "Select which files, if any, you want to use."
        )

    @property
    def run_wizard(self) -> bool:
        """True if the wizard has anything to present (VB ``RunWizard``)."""
        return bool(self.select_one or self.select_many or self.installer_excludes)


def _filename_only(line: str) -> str:
    """Stem of the last path component (VB ``FilenameOnly``; ``\\`` or ``/`` paths)."""
    return PurePosixPath(line.replace("\\", "/")).stem


def _default_display(line: str) -> str:
    """Derive a display name from a path (VB ``FilenameOnly.ToSentence("_").ToTitleCase``)."""
    words = _filename_only(line).replace("_", " ").split()
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _item_info(line: str) -> tuple[str, str]:
    """(relative path, display name) for a statement line (VB ``GetItemInfo``)."""
    line = line.strip()
    fields = line.split(_NAME_SEPARATOR)
    if len(fields) > 1:
        return fields[0].strip(), fields[1].strip()
    return line, _default_display(line)


def parse_wizard_text(text: str, mod_name: str = "") -> WizardInfo:
    """Parse wizard-definition ``text`` into a :class:`WizardInfo` (VB ``Load`` loop)."""
    info = WizardInfo(mod_name=mod_name)
    select_type = ""
    for raw in text.splitlines():
        line = raw.strip().strip("\t").strip()

        # Ignore blank, comment ('), and region (#) lines.
        if line == "" or line.startswith("'") or line.startswith("#"):
            continue

        lower = line.lower()

        # Keywords with no trailing information (case-insensitive; VB Option Compare Text).
        if lower == _EXTRACT_ARCHIVES.lower():
            info.extract_archives = True
            continue
        if lower == _SELECT_ONE.lower():
            select_type = _SELECT_ONE
            continue
        if lower == _SELECT_MANY.lower():
            select_type = _SELECT_MANY
            continue
        if lower == _INSTALLER_EXCLUDES.lower():
            select_type = _INSTALLER_EXCLUDES
            continue
        if lower in (
            _END_SELECT_ONE.lower(),
            _END_SELECT_MANY.lower(),
            _END_INSTALLER_EXCLUDES.lower(),
        ):
            select_type = ""
            continue

        # File-name lines belonging to the active block.
        if select_type == _SELECT_ONE:
            key, display = _item_info(line)
            info.select_one.setdefault(key, display)
            continue
        if select_type == _SELECT_MANY:
            _add_select_many(info, line)
            continue
        if select_type == _INSTALLER_EXCLUDES:
            info.installer_excludes.append(line)
            continue

        # Keyword-with-text lines (only reached outside a block).
        if lower.startswith(_WIZARD_TITLE.lower()):
            info.title_value = line.split("=", 1)[1].strip()
        elif lower.startswith(_SELECT_ONE.lower()):
            select_type = _SELECT_ONE
            info.select_one_text_value = line.split("=", 1)[1].strip()
        elif lower.startswith(_SELECT_MANY.lower()):
            select_type = _SELECT_MANY
            info.select_many_text_value = line.split("=", 1)[1].strip()

    return info


def _add_select_many(info: WizardInfo, line: str) -> None:
    """Parse a SelectMany line ``path > Name = Checked`` (VB ``AddSelectMany``)."""
    fields = line.split("=")
    key, display = _item_info(fields[0])
    checked = len(fields) > 1 and fields[1].strip().lower() == "checked"
    info.select_many.append(WizardPreference(key=key, display=display, checked=checked))


def load_wizard(mod_folder: Path, mod_name: str = "") -> WizardInfo | None:
    """Load the wizard for a mod folder, or ``None`` if absent/unreadable (VB ``Load``)."""
    wizard_file = mod_folder / WIZARD_FILE
    if not wizard_file.is_file():
        return None
    try:
        text = wizard_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_wizard_text(text, mod_name)


# -- Serialisation (VB ConvertToText) -------------------------------------- #


def convert_to_text(info: WizardInfo) -> str:
    """Serialise a :class:`WizardInfo` to wizard-file text (VB ``ConvertToText``).

    Mirrors the VB layout exactly: a leading blank line, ``WizardTitle = <title>``,
    then the ``ExtractArchives`` flag and each block. Note SelectOne is only written
    when it has **more than one** entry (VB "must be at least two to be meaningful");
    the display defaults (title / instruction texts) come from the getters.
    """
    parts: list[str] = ["\n", f"{_WIZARD_TITLE} = {info.title}", "\n", "\n"]

    if info.extract_archives:
        parts += [_EXTRACT_ARCHIVES, "\n"]

    if len(info.select_one) > 1:
        parts += [f"{_SELECT_ONE} = {info.select_one_text}", "\n"]
        for key, value in info.select_one.items():
            parts += [f"\t{key} {_NAME_SEPARATOR} {value}", "\n"]
        parts += [_END_SELECT_ONE, "\n"]
        if info.select_many:
            parts += ["\n"]

    if info.select_many:
        parts += [f"{_SELECT_MANY} = {info.select_many_text}", "\n"]
        for pref in info.select_many:
            state = "Checked" if pref.checked else "Unchecked"
            parts += [
                f"\t{pref.key} {_NAME_SEPARATOR} {pref.display} = {state}",
                "\n",
            ]
        parts += [_END_SELECT_MANY, "\n"]

    if info.installer_excludes:
        parts += [_INSTALLER_EXCLUDES, "\n"]
        for filename in info.installer_excludes:
            parts += [f"\t{filename}", "\n"]
        parts += [_END_INSTALLER_EXCLUDES, "\n"]

    return "".join(parts)


def save_wizard(mod_folder: Path, info: WizardInfo) -> bool:
    """Write ``info`` to the mod's wizard file (VB ``Save``). True on success."""
    try:
        (mod_folder / WIZARD_FILE).write_text(convert_to_text(info), encoding="utf-8")
    except OSError:
        return False
    return True


def delete_wizard(mod_folder: Path, *, to_trash: bool = False) -> bool:
    """Delete the mod's wizard file (VB ``Delete``). True if a file was removed."""
    from vaultkeeper.core import fs

    wizard_file = mod_folder / WIZARD_FILE
    if not wizard_file.is_file():
        return False
    try:
        fs.delete(wizard_file, to_trash=to_trash, missing_ok=True)
    except OSError:
        return False
    return True


# -- File scan + validation (VB ScanFiles / Validate) ---------------------- #


class ExtractType(IntEnum):
    """How a source file is obtained (VB ``WizardInfo.ExtractType``)."""

    FILES = 0
    FOLDERS = 1
    FOLDER_FILES = 2


@dataclass
class ScanResult:
    """Outcome of scanning a mod's real files (VB ``ScanFiles`` output)."""

    #: Eligible source files keyed by mod-relative path (``\\`` separators, VB style).
    source_files: dict[str, ExtractType] = field(default_factory=dict)
    #: Archive files found loose in the mod (VB ``ArchiveList``); not yet extracted.
    archives: list[Path] = field(default_factory=list)
    #: True if a duplicate file/archive name was found (VB ``SuppressWizardCreation``).
    suppressed: bool = False
    #: The duplicate name that triggered suppression, if any.
    duplicate: str = ""


def _is_hidden(name: str) -> bool:
    """Cross-platform proxy for VB's Hidden/System attribute check (dot-prefixed)."""
    return name.startswith(".")


def _is_reserved_file(name: str) -> bool:
    """VB ``Paths.IsReservedName`` for the reserved *files* (dot-named markers)."""
    return name.lower() in (C.PLAY_TIME_FILE.lower(), WIZARD_FILE.lower())


def _relative_key(sub_dir: str, name: str) -> str:
    """Mod-relative key ``<sub_dir>\\<name>`` with leading separators trimmed."""
    return f"{sub_dir}\\{name}".lstrip("\\")


def scan_mod_files(
    mod_folder: Path,
    *,
    is_installable,
    is_excluded_folder,
) -> ScanResult:
    """Enumerate a mod's Create-Installer-eligible source files (VB ``ScanFiles``).

    Walks ``mod_folder`` top-down. Archives (``is_zip_extension``) are recorded by
    name (``ExtractType.FILES``) and collected in :attr:`ScanResult.archives`; other
    files are kept when ``is_installable(path)`` is true (VB
    ``Map.GetMappedFolder(fi, True) <> ""``), keyed by their mod-relative path.
    Hidden/system files and reserved names are skipped; recursion skips excluded
    folders (``is_excluded_folder(name)``) and does not append ``_Downloads`` /
    ``_Published`` to the relative path (matching VB). A duplicate file/archive name
    sets :attr:`ScanResult.suppressed` and stops the scan (VB
    ``SuppressWizardCreation``). Archives are **not** extracted — their contents are
    validated only once the extract pass (``ProcessArchive``) is ported.
    """
    result = ScanResult()
    _scan_dir(
        mod_folder,
        result,
        sub_dir="",
        is_installable=is_installable,
        is_excluded_folder=is_excluded_folder,
    )
    return result


def _scan_dir(
    folder: Path,
    result: ScanResult,
    *,
    sub_dir: str,
    is_installable,
    is_excluded_folder,
) -> None:
    present = {k.lower() for k in result.source_files}
    for fi in sorted(p for p in folder.iterdir() if p.is_file()):
        name = fi.name
        if _is_hidden(name) or _is_reserved_file(name):
            continue
        if is_zip_extension(fi.suffix):
            if name.lower() in present:
                result.suppressed = True
                result.duplicate = name
                return
            result.source_files[name] = ExtractType.FILES
            present.add(name.lower())
            result.archives.append(fi)
        elif is_installable(fi):
            key = _relative_key(sub_dir, name)
            if key.lower() in present:
                result.suppressed = True
                result.duplicate = name
                return
            result.source_files[key] = ExtractType.FILES
            present.add(key.lower())

    if result.suppressed:
        return

    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        if is_excluded_folder(sub.name):
            continue
        # _Downloads / _Published are traversed but not added to the relative path.
        if sub.name in (C.DOWNLOADS_DIR, C.PUBLISHED_DIR):
            child_sub = sub_dir
        else:
            child_sub = _relative_key(sub_dir, sub.name)
        _scan_dir(
            sub,
            result,
            sub_dir=child_sub,
            is_installable=is_installable,
            is_excluded_folder=is_excluded_folder,
        )
        if result.suppressed:
            return


# -- Publish rewrite (VB PublishMod wizard update) ------------------------- #

#: Characters stripped from the archive-folder qualifier (VB AppDefs
#: ``VaultArchiveRemoveChars`` = apostrophe + space; spaces are already replaced
#: with ``_`` first, so in practice this removes apostrophes).
_VAULT_ARCHIVE_REMOVE_CHARS = "' "


def archive_folder_name(zip_file_name: str) -> str:
    """Folder qualifier a published archive extracts to (VB ``archiveFolder``).

    Lower-cases the ``.7z`` name, replaces spaces with ``_`` and strips the
    ``VaultArchiveRemoveChars`` (apostrophes).
    """
    name = zip_file_name.lower().replace(" ", "_")
    for ch in _VAULT_ARCHIVE_REMOVE_CHARS:
        name = name.replace(ch, "")
    return name


def rewrite_for_publish(wizard_text: str, archive_folder: str) -> str:
    """Rewrite a wizard's file references for a published archive (VB ``BtPublish``).

    Every SelectOne/SelectMany/InstallerExcludes file entry is re-rooted under
    ``archive_folder`` (the folder the published ``.7z`` extracts to), replacing any
    existing archive prefix; ``ExtractArchives`` is forced on (inserted right after
    ``WizardTitle``, any existing flag dropped). Block header/footer lines and the
    title are preserved. The caller restores the original file afterwards.
    """
    start_block = {
        _SELECT_ONE.lower(),
        _SELECT_MANY.lower(),
        _INSTALLER_EXCLUDES.lower(),
    }
    end_block = {
        _END_SELECT_ONE.lower(),
        _END_SELECT_MANY.lower(),
        _END_INSTALLER_EXCLUDES.lower(),
    }

    out: list[str] = []
    folder_prefix = False
    for wizard_line in wizard_text.splitlines():
        raw = wizard_line.replace("\t", "")
        keyword = raw.split("=", 1)[0].strip().lower()

        if keyword == _WIZARD_TITLE.lower():
            out.append(wizard_line)  # keep the title
            wizard_line = _EXTRACT_ARCHIVES  # then force ExtractArchives on
        elif keyword == _EXTRACT_ARCHIVES.lower():
            continue  # drop any existing flag (re-inserted after the title)
        elif keyword in start_block:
            folder_prefix = True
        elif keyword in end_block:
            folder_prefix = False
        elif folder_prefix and raw != "":
            slash = raw.find("\\")
            tab_count = len(wizard_line) - len(raw)
            if slash > 0 and is_zip_extension(PurePosixPath(raw[:slash]).suffix):
                raw = raw[slash + 1 :]  # strip an existing archive prefix
            wizard_line = "\t" * tab_count + f"{archive_folder}\\{raw}"

        out.append(wizard_line)

    return "\n".join(out) + "\n"


def validate(info: WizardInfo, source_files: dict[str, ExtractType]) -> int:
    """Prune wizard entries whose file no longer exists (VB ``Validate``).

    Mutates ``info`` in place: removes SelectOne / SelectMany / InstallerExcludes
    entries whose relative path is not present in ``source_files`` (case-insensitive,
    VB dict semantics). Returns the number of entries removed.
    """
    present = {k.lower() for k in source_files}
    removed = 0

    for key in list(info.select_one.keys()):
        if key.lower() not in present:
            del info.select_one[key]
            removed += 1

    for i in range(len(info.select_many) - 1, -1, -1):
        if info.select_many[i].key.lower() not in present:
            del info.select_many[i]
            removed += 1

    for i in range(len(info.installer_excludes) - 1, -1, -1):
        if info.installer_excludes[i].lower() not in present:
            del info.installer_excludes[i]
            removed += 1

    return removed
