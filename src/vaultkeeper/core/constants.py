"""Core domain constants, ported faithfully from the VB app.

Sourced from ``Defs.vb``, ``Paths.vb``, ``ProfileData.*`` and ``Mapper.vb``.
Values that are part of the *data contract* (reserved names, folder markers,
group names) must match the original so a migrated store and the game folder are
interpreted identically. Vaultkeeper-specific presentation strings live
elsewhere; this module is the domain vocabulary only.
"""

from __future__ import annotations

from typing import Final

# --- Identity ------------------------------------------------------------- #
#: Original tool's acronym, retained where it appears in on-disk artifacts.
NIT_ACRONYM: Final = "NIT"

# --- Reserved group rows (ModList keys that are groups, not mods) --------- #
# These are LazWorks FileView sentinel strings (not friendly names): the control
# uses a "......" hidden-group prefix. Verified against LazWorks
# (FileViewGroupHidden="......", FileViewGroupHide=+"000", FileViewGroupNone=+"001")
# and Defs.vb (GroupInstalled=FileViewGroupHide, GroupNone=FileViewGroupNone).
# They are persisted verbatim as ModList keys, so they MUST match exactly.
_FILEVIEW_GROUP_HIDDEN: Final = "......"
#: Public alias: group keys with this prefix are *hidden* groups — the FileView shows
#: their mods at the top level with no group header (LazWorks FileView.GroupManager
#: skips ``group.StartsWith(FileViewGroupHidden)`` when adding group rows).
GROUP_HIDDEN_PREFIX: Final = _FILEVIEW_GROUP_HIDDEN
#: The reserved "Installed" group key (Defs.GroupInstalled = FileViewGroupHide).
GROUP_INSTALLED: Final = _FILEVIEW_GROUP_HIDDEN + "000"
#: The "no group" bucket key (Defs.GroupNone = FileViewGroupNone).
GROUP_NONE: Final = _FILEVIEW_GROUP_HIDDEN + "001"
#: Human-readable label for the installed-files pseudo-mod ("Installed Files").
INSTALLED_FILES_LABEL: Final = "Installed Files"
#: Key of the installed-files pseudo-mod (Defs.InstalledModKey). Note the "/" join.
INSTALLED_MOD_KEY: Final = GROUP_INSTALLED + "/" + INSTALLED_FILES_LABEL
#: Mandatory groups that must exist; their absence signals a corrupt profile DB.
MANDATORY_GROUPS: Final = (GROUP_NONE, GROUP_INSTALLED)

# --- Mod folder layout (subfolders inside a mod directory) ---------------- #
#: The installer payload folder — files here are what get copied into the game.
MOD_INSTALLER_DIR: Final = ".Mod Installer"
#: Downloaded archives awaiting installer creation.
DOWNLOADS_DIR: Final = "_Downloads"
#: Superseded/previous downloads.
HISTORY_DIR: Final = "_History"
#: Published (distributable) packages.
PUBLISHED_DIR: Final = "_Published"
#: Steam Workshop-managed content.
WORKSHOP_DIR: Final = "_Workshop"
#: Quarantine for files that violate mapping rules.
REMOVED_ITEMS_DIR: Final = ".Removed Items"
#: Per-mod durable play-time record (RTF).
PLAY_TIME_FILE: Final = ".Game Play Time.rtf"
#: Installer wizard definition file (Paths.C.WizardFile = ".Installer Wizard" + ".nitwiz").
WIZARD_FILE: Final = ".Installer Wizard.nitwiz"
#: The nit config subfolder holding a mod's identifier files (Pdc.ModNit).
MOD_NIT_DIR: Final = "nitconfig"
#: Normalised name the game-root folder maps to inside a FileKey (Mapper.C.ModRoot).
MOD_ROOT_FOLDER: Final = "nwn"

# --- Game subfolder names (Mapper.C) -------------------------------------- #
#: The game's ``modules`` folder (Mapper.C.ModFolder).
MOD_FOLDER: Final = "modules"
#: The game's ``nwm`` folder for premium modules (Mapper.C.ModNwmFolder).
MOD_NWM_FOLDER: Final = "nwm"

# --- Hak patch ini filenames (NwnFolderInfo) ------------------------------ #
PATCH_INI_FILE: Final = "nwnpatch.ini"
USER_PATCH_INI_FILE: Final = "userpatch.ini"

# --- Special log filenames (installer classification) --------------------- #
LETO_LOG_FILENAME: Final = "LoadITPLog.leto.txt"
NWN_LOG_FILENAME: Final = "AR_ERROR.LOG"

# --- Sentinel integer ----------------------------------------------------- #
#: "not specified" for optional integer mod properties (Pdc.NullValue).
NULL_VALUE: Final = -1

# --- File extensions (data contract) -------------------------------------- #
#: Module file extension (Mapper.C.ModFile); ``.nwm`` is the other module type.
EXT_MOD: Final = ".mod"
EXT_NWM: Final = ".nwm"
#: ERF archive extension (extracted on install, so leftover ``.erf`` files are removable).
EXT_ERF: Final = ".erf"
#: Installer identifier-file extension (Pdc.ExtInstaller).
EXT_INSTALLER: Final = ".nitins"
#: Restorer identifier-file extension (Pdc.ExtRestorer).
EXT_RESTORER: Final = ".nitres"

#: Reserved folder names that can never be mod names.
RESERVED_MOD_NAMES: Final = frozenset(
    {
        DOWNLOADS_DIR,
        HISTORY_DIR,
        PUBLISHED_DIR,
        WORKSHOP_DIR,
    }
)

# --- Original-restorer groups / mod names (ProfileData.Defs) --------------- #
#: Group the auto-created original restorers land in (Pdc.RestorerGroup).
RESTORER_GROUP: Final = "000.  Restorers"
#: Group for the base-game modules NWN itself installed (Pdc.OriginalModsGroup).
ORIGINAL_MODS_GROUP: Final = "799.  Mods Installed by NWN"
#: The three fixed original-file restorer mod names (Pdc.*Restorer).
CORE_FILES_RESTORER: Final = "1.  NWN Core Files Restorer"
INI_FILES_RESTORER: Final = "2.  NWN INI Files Restorer"
CHARACTER_FILES_RESTORER: Final = "3.  NWN Character Files Restorer"

# --- Installer sentinel names (InstalledFileData.Installer values) -------- #
#: File is an unmodified game-shipped original (Pdc.ModOriginal).
INSTALLER_ORIGINAL: Final = "Neverwinter Nights installation"
#: File is a saved character (Pdc.ModCharacter).
INSTALLER_CHARACTER: Final = "Saved character"
#: Journal notes file (Pdc.ModJournalNotes).
INSTALLER_JOURNAL_NOTES: Final = "Journal notes"
#: NWN log file (Pdc.NwnLogFile).
INSTALLER_NWN_LOG: Final = "Neverwinter Nights log file"
#: Leto log file (Pdc.LetoLogFile).
INSTALLER_LETO_LOG: Final = "Leto log file"
#: Installer source is unknown (Pdc.ModUnknown).
INSTALLER_UNKNOWN: Final = "Unknown source"
#: Sentinel requesting the owning-mod resolution logic run (Pdc.FindInstaller).
INSTALLER_FIND: Final = "\\FindInstaller\\"

#: The set of "default" (non-user-mod) installer names, sorted for lookup.
DEFAULT_INSTALLERS: Final = frozenset(
    {
        INSTALLER_ORIGINAL,
        INSTALLER_CHARACTER,
        INSTALLER_JOURNAL_NOTES,
        INSTALLER_NWN_LOG,
        INSTALLER_LETO_LOG,
        INSTALLER_UNKNOWN,
    }
)

# --- On-disk data versions ------------------------------------------------ #
#: VB BinaryFormatter data-format version (for the legacy NRBF importer only).
LEGACY_DATA_FORMAT_VERSION: Final = 2
#: Mapper table version in the VB app (``Mapper.vb`` MapVersion).
LEGACY_MAP_VERSION: Final = 21
#: Vaultkeeper's own native store schema version (independent of the legacy one).
NATIVE_STORE_VERSION: Final = 1

# --- Install engine invariants (from ModInstallationManager.vb) ----------- #
#: Files strictly smaller than this are always copied even when the CRC matches,
#: guarding against CRC-32 collisions on tiny files. VB constant = 5121 (5 KB + 1).
NO_CRC_CHECK_MAX_BYTES: Final = 5121

# --- Path separator contract --------------------------------------------- #
#: FileKeys persist a backslash separator regardless of host OS; normalise only
#: at the filesystem boundary. (VB stored "Folder\Filename".)
FILEKEY_SEPARATOR: Final = "\\"
