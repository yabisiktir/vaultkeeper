"""Mod Installer Wizard definitions (VB ``WizardInfo`` / ``WizardBuilder``).

A *wizard* is a small text file (``.Installer Wizard.nitwiz``) stored in a mod's
root folder that customises how the mod's installer behaves: an optional title,
whether archives must be extracted first, a **SelectOne** group (mutually-exclusive
"choices"), a **SelectMany** group (optional "preferences" with default checked
state), and an **InstallerExcludes** list (files the Create-Installer step skips).

This module is the headless read model: it parses that file into a :class:`WizardInfo`.
It is a faithful port of ``WizardInfo.Load`` / ``GetItemInfo`` / ``AddSelectOne`` /
``AddSelectMany`` (``WizardInfo.vb``); ``Option Compare Text`` makes keyword matching
case-insensitive. The *authoring* side (Save/Delete, and Validate/ScanFiles/
ProcessArchive which walk the mod's real files and archives to check the statements)
is deferred with the WizardBuilder editing UI — see the handoff.

The LazWorks string helpers ``FilenameOnly``/``ToSentence("_")``/``ToTitleCase`` used
to derive a default display name are not present in the source tree; their behaviour
is reconstructed from usage (drop the folder+extension, ``_``→space, title-case).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

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
