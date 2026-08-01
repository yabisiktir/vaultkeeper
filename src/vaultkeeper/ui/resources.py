"""Resource loader — QIcon/QPixmap access to the bundled NIT image assets.

Ported from the VB ``My.Resources`` access layer. The images under
``ui/resources/images/`` are the original project's own assets, copied verbatim so
the UI is pixel-identical. Code names map to file names via :data:`ICON_NAME_MAP`,
with a spaces<->underscores fallback covering the many icons referenced by name.
"""

from __future__ import annotations

from pathlib import Path

from nwnfile.log import get_logger
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

log = get_logger(__name__)

#: Directory holding the bundled image assets.
RESOURCES_PATH = Path(__file__).parent / "resources" / "images"

#: Extensions tried when resolving a resource name to a file.
_EXTENSIONS = (".png", ".ico", ".gif", ".svg")

_icon_cache: dict[str, QIcon] = {}
_pixmap_cache: dict[str, QPixmap] = {}


ICON_NAME_MAP = {
    # Special cases where file names don't match icon names
    "NIT_Icon_v5_006c": "NIT Icon v5-006c",
    "Export_Arrow": "Export Arrow",
    "Profiles": "Profiles",
    "Folder_6221": "Folder_6221",
    "DOWNLOAD_PROJECT_16X": "DownloadProject_16x",
    "MOVE_TO_FOLDER_HS": "MoveToFolderHS",
    "ADD_MOD_FILES": "AddModFiles",
    "DOWNLOAD_FOLDER_16X": "DownloadFolder_16x",
    "FILE_COPY_16": "FileCopy16",
    "FILE_HISTORY": "FileHistory",
    "DEVELOPER_MODE_16X": "DeveloperMode_16x",
    "NOTE_PAD": "NotePad",
    "WORD_PAD": "WordPad",
    "EXPORT_DATA_16X": "ExportData_16x",
    "WRITE_TO_DATABASE_16X": "WriteToDatabase_16x",
    "ARROW_IMPORT_OR_LOAD_16X_COLOR": "Arrow_ImportOrLoad_16x_color",
    "NIT_ICON_V5_006C": "NIT_Icon_v5_006c",
    "CONNECT_16X": "Connect_16x",
    "EXTRACT_METHOD_6786": "ExtractMethod_6786",
    "PROPERTIES_W10": "PropertiesW10",
    "RESTART_GREEN_16X": "Restart_Green_16x",
    "EXIT_APP": "ExitApp",
    "HISTORY_16X": "History_16x",
    "COPY_HS": "CopyHS",
    "COPY_NAME": "CopyName",
    "PASTE_006": "Paste-006",
    "DELETE": "Delete",
    "RENAME_BLACK": "RenameBlack",
    "FIND_5650": "Find_5650",
    "FIND_AND_REPLACE": "FindAndReplace",
    "GROUP": "Group",
    "CONVERT_RESTORER": "CreateRestorer_x32",
    "COPY_URL_LINK_16X": "CopyUrlLink_16x",
    "REFRESH_ARROW_BLUE": "Refresh Arrow Blue",
    "EXPAND_MENU_IMAGE": "Expand Menu Image",
    "COLLAPSE_MENU_IMAGE": "Collapse Menu Image",
    "CHARACTER_SUMMARY": "UserProfile_16x",
    "MODS_PLAYED": "PlayTime_16x",
    "CONFLICTS": "ValidateMods",
    "WORKSHOP_VIEWER": "SteamViewer",
    "LOG_FILE": "Log File",
    "DISPLAY_SETTINGS": "Customiser",
    "NEW_GROUP": "action_add_16xLG",
    "MOVE_TO_GROUP": "MoveTo",
    "NEW_MOD": "CreateModFolder_32x",
    "LOADSCREENS": "AddImage",
    "HAK_PATCH_EDITOR": "PatchPackage_16x",
    "ANNEAL": "Anneal_16x",
    "SYNCHRONIZE": "SynchronizeDatabase_16x",
    "COMPACT": "Defrag",
    "INSTALL": "Install Package 16x16",
    "UNINSTALL": "Uninstall",
    "MOD_EXPLORER": "Mod Explorer 1",
    "CHARACTER_EXPLORER": "user",
    "INSTALLATION_MANAGER": "ManageBackups16",
    "DEPENDENCY_MANAGER": "DependencyGraph_16x",
    "PORTRAIT_MANAGER": "CameraBlue_16x",
    "BACKUP_MANAGER": "ManageBackups16",
    "SETTINGS": "Settings-006",
    "SETTINGS_BLUE_COG_32": "SettingsBlueCog32",
    "PLAY_NWN": "PlayBlue32x",
    "TOOLSET": "Hammer_Builder_16xLG",
    "PLAY_DM": "Play32x32",
    "NEVERWINTER_VAULT": "Web_16x",
    "CHECK_UPDATES": "UpdateNow_16x",
    "FONT_AND_COLOUR": "fontandcolour x16x",
    "ORIGINAL_PORTRAITS": "OriginalRestorer",
    "RESET_16X": "Reset_16x",
    "DEBUG": "Debug",
    "HELP_ICON": "HelpIcon",
    "WELCOME_SAMPLE_FOLDER_32X": "WelcomeSampleFolder_32x",
    "FAQ_1": "FAQ 1",
    "WHATS_NEW_16X": "WhatsNew_16x",
    "HISTORY": "History",
    "CLASSES_SKILLS_FEATS": "FeatInfo_x16",
    "UPDATE_NOW_16X": "UpdateNow_16x",
    "SEND_EMAIL_16X": "SendEmail_16x",
    "SELECT_ALL": "SelectAll",
    "CUT_006": "Cut-006",
    "WEB_INSERT_HYPERLINK_HS": "WebInsertHyperlinkHS",
    "NIT_ICON": "NIT Icon v5",
    "NIT_ICON_8": "NIT Icon 8",
    # Add more mappings as needed when mismatches are found
}


def _candidate_names(name: str) -> list[str]:
    """Names to try for a resource: mapped, literal, and space/underscore swaps."""
    names = [ICON_NAME_MAP.get(name, name), name]
    names.append(name.replace("_", " "))
    names.append(name.replace(" ", "_"))
    seen: dict[str, None] = {}
    for n in names:
        seen.setdefault(n, None)
    return list(seen)


def _normalise(stem: str) -> str:
    """Collapse a name to compare across space/underscore/dash variants."""
    return "".join(ch for ch in stem.lower() if ch.isalnum())


_normalised_index: dict[str, Path] | None = None


def _index() -> dict[str, Path]:
    """Lazy index of every asset by its normalised stem.

    The VB ``My.Resources`` generator turns spaces *and* dashes into underscores, so
    a code name like ``NIT_Icon_v5_006c`` can back a file called
    ``NIT Icon v5-006c.png``. Matching on the normalised stem resolves every such
    variant without a hand-maintained map entry.
    """
    global _normalised_index
    if _normalised_index is None:
        _normalised_index = {}
        if RESOURCES_PATH.is_dir():
            for path in sorted(RESOURCES_PATH.iterdir()):
                if path.suffix.lower() in _EXTENSIONS:
                    _normalised_index.setdefault(_normalise(path.stem), path)
    return _normalised_index


def resolve_path(name: str) -> Path | None:
    """Return the file backing ``name``, or ``None`` if no asset matches."""
    for candidate in _candidate_names(name):
        for ext in _EXTENSIONS:
            path = RESOURCES_PATH / f"{candidate}{ext}"
            if path.exists():
                return path
    # Final fallback: match ignoring spaces/underscores/dashes/case.
    return _index().get(_normalise(ICON_NAME_MAP.get(name, name)))


def get_icon(name: str) -> QIcon:
    """Return a cached :class:`QIcon` for ``name`` (empty icon if absent)."""
    cached = _icon_cache.get(name)
    if cached is not None:
        return cached
    path = resolve_path(name)
    icon = QIcon(str(path)) if path is not None else QIcon()
    if path is None:
        log.debug("Icon not found: %s", name)
    _icon_cache[name] = icon
    return icon


def get_pixmap(name: str) -> QPixmap:
    """Return a cached :class:`QPixmap` for ``name`` (empty pixmap if absent)."""
    cached = _pixmap_cache.get(name)
    if cached is not None:
        return cached
    path = resolve_path(name)
    pixmap = QPixmap(str(path)) if path is not None else QPixmap()
    if path is None:
        log.debug("Pixmap not found: %s", name)
    _pixmap_cache[name] = pixmap
    return pixmap


def icon_exists(name: str) -> bool:
    """True if an asset backs ``name``."""
    return resolve_path(name) is not None


#: Largest first: QIcon picks per context, and shipping the big ones is what
#: stops a Retina dock scaling a small image up.
_APP_ICON_SIZES = (1024, 512, 256, 128, 64, 48, 32, 16)


def app_icon_dir() -> Path | None:
    """Where the generated application icons live, in a checkout or a build.

    A frozen build unpacks its data beside the executable (``sys._MEIPASS``)
    rather than next to the source, so both are looked at.
    """
    import sys

    frozen = getattr(sys, "_MEIPASS", None)
    roots = [Path(frozen) / "assets" / "icons"] if frozen else []
    roots.append(Path(__file__).resolve().parents[3] / "assets" / "icons")
    return next((root for root in roots if root.is_dir()), None)


def app_icon() -> QIcon:
    """The application/window icon, at every size we ship.

    This used to return a lone 16x16 PNG, which every larger context then scaled
    up — the taskbar and the window switcher both look wrong that way. The
    generated set (``scripts/make_icons.py``) runs 16 to 1024, so each context
    gets a real image. Falls back to the inherited artwork if the generated
    assets are missing, so a bare checkout still shows something.
    """
    root = app_icon_dir()
    if root is None:
        return get_icon("NIT Icon 8")  # the multi-size inherited .ico
    icon = QIcon()
    for size in _APP_ICON_SIZES:
        path = root / f"icon_{size}.png"
        if path.is_file():
            icon.addFile(str(path))
    return icon if not icon.isNull() else get_icon("NIT Icon 8")


def sized_icon(name: str, size: int) -> QIcon:
    """An icon forced to a single square pixel size (for crisp toolbar images)."""
    pixmap = get_pixmap(name)
    if pixmap.isNull():
        return QIcon()
    return QIcon(pixmap.scaled(QSize(size, size)))


class Icons:
    """Icon resource names matching VB.NET My.Resources"""
    
    # Menu icons - File menu
    PROFILES = "Profiles"
    FOLDER_6221 = "Folder_6221"
    DOWNLOAD_PROJECT_16X = "DownloadProject_16x"
    MOVE_TO_FOLDER_HS = "MoveToFolderHS"
    ADD_MOD_FILES = "AddModFiles"
    DOWNLOAD_FOLDER_16X = "DownloadFolder_16x"
    FILE_COPY_16 = "FileCopy16"
    FILE_HISTORY = "FileHistory"
    DEVELOPER_MODE_16X = "DeveloperMode_16x"
    ADD_FOLDER = "AddFolder"
    NOTE_PAD = "NotePad"
    WORD_PAD = "WordPad"
    EXPORT_DATA_16X = "ExportData_16x"
    WRITE_TO_DATABASE_16X = "WriteToDatabase_16x"
    EXPORT_ARROW = "Export_Arrow"
    ARROW_IMPORT_OR_LOAD_16X_COLOR = "Arrow_ImportOrLoad_16x_color"
    NIT_ICON_V5_006C = "NIT_Icon_v5_006c"
    CONNECT_16X = "Connect_16x"
    EXTRACT_METHOD_6786 = "ExtractMethod_6786"
    PROPERTIES_W10 = "PropertiesW10"
    RESTART_GREEN_16X = "Restart_Green_16x"
    EXIT_APP = "ExitApp"
    HISTORY_16X = "History_16x"
    
    # Edit menu
    COPY_HS = "CopyHS"
    COPY_NAME = "CopyName"
    PASTE_006 = "Paste-006"
    DELETE = "Delete"
    RENAME_BLACK = "RenameBlack"
    FIND_5650 = "Find_5650"
    FIND_AND_REPLACE = "FindAndReplace"
    GROUP = "Group"
    CONVERT_RESTORER = "CreateRestorer_x32"
    COPY_URL_LINK_16X = "CopyUrlLink_16x"
    
    # View menu
    REFRESH_ARROW_BLUE = "Refresh Arrow Blue"
    EXPAND_MENU_IMAGE = "Expand Menu Image"
    COLLAPSE_MENU_IMAGE = "Collapse Menu Image"
    CHARACTER_SUMMARY = "UserProfile_16x"
    MODS_PLAYED = "PlayTime_16x"
    CONFLICTS = "ValidateMods"
    WORKSHOP_VIEWER = "SteamViewer"
    LOG_FILE = "Log File"
    DISPLAY_SETTINGS = "Customiser"
    
    # Manage menu
    NEW_GROUP = "action_add_16xLG"
    MOVE_TO_GROUP = "MoveTo"
    NEW_MOD = "CreateModFolder_32x"
    LOADSCREENS = "AddImage"
    HAK_PATCH_EDITOR = "PatchPackage_16x"
    ANNEAL = "Anneal_16x"
    SYNCHRONIZE = "SynchronizeDatabase_16x"
    COMPACT = "Defrag"
    INSTALL = "Install Package 16x16"
    UNINSTALL = "Uninstall"
    
    # Tools menu
    MOD_EXPLORER = "Mod Explorer 1"
    CHARACTER_EXPLORER = "user"
    INSTALLATION_MANAGER = "ManageBackups16"
    DEPENDENCY_MANAGER = "DependencyGraph_16x"
    PORTRAIT_MANAGER = "CameraBlue_16x"
    BACKUP_MANAGER = "ManageBackups16"
    SETTINGS = "Settings-006"
    SETTINGS_BLUE_COG_32 = "SettingsBlueCog32"
    
    # Run menu
    PLAY_NWN = "PlayBlue32x"
    TOOLSET = "Hammer_Builder_16xLG"
    PLAY_DM = "Play32x32"
    
    # Web menu
    NEVERWINTER_VAULT = "Web_16x"
    CHECK_UPDATES = "UpdateNow_16x"
    
    # Options menu
    FONT_AND_COLOUR = "fontandcolour x16x"
    ORIGINAL_PORTRAITS = "OriginalRestorer"
    RESET_16X = "Reset_16x"
    DEBUG = "Debug"
    
    # Help menu
    HELP_ICON = "HelpIcon"
    WELCOME_SAMPLE_FOLDER_32X = "WelcomeSampleFolder_32x"
    FAQ_1 = "FAQ 1"
    WHATS_NEW_16X = "WhatsNew_16x"
    HISTORY = "History"
    CLASSES_SKILLS_FEATS = "FeatInfo_x16"
    UPDATE_NOW_16X = "UpdateNow_16x"
    SEND_EMAIL_16X = "SendEmail_16x"
    
    # Edit menu extras
    SELECT_ALL = "SelectAll"
    CUT_006 = "Cut-006"
    WEB_INSERT_HYPERLINK_HS = "WebInsertHyperlinkHS"
    
    # Window icons
    NIT_ICON = "NIT Icon v5"
    NIT_ICON_8 = "NIT Icon 8"
    
    # Additional icons for ribbon
    CHANGE_INSTALLER = "FindAndReplace"  # Placeholder
    DOC_ORGANISER = "NotePad"  # Placeholder
    
    # Panel header icons - matching VB.NET exactly
    REFRESH_ARROW_BLUE_13X = "Refresh Arrow Blue_13x"  # For Details panel
    PROPERTIES_W10 = "PropertiesW10"  # For Properties panel
    
    # Panel header icon aliases
    DETAILS_PANEL = "Refresh Arrow Blue_13x"
    PROPERTIES_PANEL = "PropertiesW10"
    NOTE = "FeatInfo_x16"  # Notes uses the feat-info icon


# Convenience function to get icons by their attribute name
