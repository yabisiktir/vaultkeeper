"""Ribbon — the tabbed command bar, faithful to the VB ``TbRibbon``.

Ported from ``NIT.Designer.vb``: seven tabs (Play, Work with Mods, Work with
Installers, Tools, Diagnose, Backup and Recovery, Customise), each a row of
``ButtonLabel`` buttons (a 32×32 image above a two-line caption). Tab titles, button
order, captions and images are taken verbatim from the designer so the ribbon is
identical to the original.

Each button carries the VB control name (``RbnPlay`` …) as its action id; clicking
emits :attr:`Ribbon.action_triggered` with that id so the controller can wire the
handlers 1:1 with the VB ``Handles`` subs.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QTabWidget,
    QToolButton,
    QWidget,
)

from vaultkeeper.ui import resources as R


@dataclass(frozen=True)
class RibbonItem:
    """One ribbon button: VB control-name id, image resource, two-line caption."""

    action: str
    image: str
    caption: str


#: The ribbon layout, verbatim from ``NIT.Designer.vb`` (tab title -> buttons).
RIBBON_TABS: tuple[tuple[str, tuple[RibbonItem, ...]], ...] = (
    ("Play", (
        RibbonItem("RbnDownloadProject", "DownloadProject_32x",
                   "Download and Install\nNeverwinter Vault Project"),
        RibbonItem("RbnPlay", "Play32x32", "Play Neverwinter\nNights"),
        RibbonItem("RbnGameSaves", "Game_Manager", "Manage your\nGame Saves"),
        RibbonItem("RbnInstallUninstall", "Install_Package_32x32", "Uninstall\nMod"),
        RibbonItem("RbnChangeInstaller", "EditInput_32x",
                   "Change Mod\nInstaller Options"),
        RibbonItem("RbnReCreateInstaller", "FolderMapping32", "Create Mod\nInstaller"),
    )),
    ("Work with Mods", (
        RibbonItem("RbnAddFiles", "MoveToFolderHS_x32x",
                   "Move Downloaded\nFiles to Selected Mod"),
        RibbonItem("RbnUpdateDownloads", "DownloadFolder_32x",
                   "Move Compressed Files to\nMod's Downloads Folder"),
        RibbonItem("RbnNewMod", "CreateModFolder_32x", "Create New\nMod Folder"),
        RibbonItem("RbnCreateInstaller", "FolderMapping32", "Create Mod\nInstaller"),
        RibbonItem("RbnToolset", "HammerBuilder_32x", "Neverwinter\nNights Toolset"),
    )),
    ("Work with Installers", (
        RibbonItem("RbnBuildInstaller", "FolderMapping32", "Create Mod\nInstaller"),
        RibbonItem("RbnWizardBuilder", "witchcraft32x32",
                   "Mod Installer\nWizard Builder"),
        RibbonItem("RbnDependencyManager", "DependencyGraph_32x",
                   "Dependency\nManager"),
        RibbonItem("RbnMapFiles", "MapFiles_32x", "Map\nFiles"),
        RibbonItem("RbnMapFolders", "MapToFolder_32x", "Map\nFolders"),
    )),
    ("Tools", (
        RibbonItem("RbnModExplorer", "Mod_Explorer_32x", "Mod\nExplorer"),
        RibbonItem("RbnInstallationManager", "checkbox_green_on32x32",
                   "Installation\nManager"),
        RibbonItem("RbnDocOrganise", "VBExtension_32x", "Organise Mod\nDocumentation"),
        RibbonItem("RbnPortraitManager", "user_32x", "Portrait\nManager"),
        RibbonItem("RbnCharacterExplorer", "LookupUser_32x", "Character\nExplorer"),
    )),
    ("Diagnose", (
        RibbonItem("RbnNwnLog", "NWN_32x32", "View Neverwinter\nNights Client Log"),
        RibbonItem("RbnNwnIni", "open_folder", "Open Neverwinter\nNights INI File"),
        RibbonItem("RbnNitLog", "NIT_Log_32x", "View Installer\nTool Log File"),
        RibbonItem("RbnDisplaySettings", "CSWorkerTemplateFile_32x",
                   "View Installer Tool\nConfiguration File"),
        RibbonItem("RbnNwnSettingsFile", "CPPMarkupXML_32x",
                   "Open Enhanced\nEdition Settings"),
        RibbonItem("RbnNwnEngineLog", "LogProperty_32x",
                   "View Neverwinter\nNights Engine Log"),
    )),
    ("Backup and Recovery", (
        RibbonItem("RbnBackupData", "ExportData_32x",
                   "Backup Installer\nTool Information"),
        RibbonItem("RbnRestoreData", "RestoreData_32x",
                   "Restore Installer\nTool Information"),
        RibbonItem("RbnExportSettings", "ExportSettings_x32", "Export your\nSettings"),
        RibbonItem("RbnCreateRestorer", "CreateRestorer_x32",
                   "Create Restorer for\nUnregistered Files"),
    )),
    ("Customise", (
        RibbonItem("RbnAdvancedSettings", "SettingsBlueCog32", "Advanced\nSettings"),
        RibbonItem("RbnBasicSettings", "SettingsCog32",
                   "Change Behaviour and\nUser Interface Preferences"),
        RibbonItem("RbnFontAndColour", "fontandcolour_x32",
                   "Change Text Size\nand Theme Colours"),
        RibbonItem("RbnManageWorkshop", "Steam32x", "Manage Steam\nWorkshop Content"),
    )),
)


class RibbonButton(QToolButton):
    """A ribbon button (VB ``ButtonLabel``): 32×32 image over a two-line caption."""

    def __init__(self, item: RibbonItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.action_id = item.action
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setText(item.caption)
        self.setIcon(R.get_icon(item.image))
        self.setIconSize(QSize(32, 32))
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(84)
        self.setMinimumHeight(64)


class Ribbon(QTabWidget):
    """The main window ribbon (VB ``TbRibbon``)."""

    #: Emitted with a button's VB control-name id when it is clicked.
    action_triggered = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.buttons: dict[str, RibbonButton] = {}
        for title, items in RIBBON_TABS:
            self.addTab(self._build_tab(items), title)

    def _build_tab(self, items: tuple[RibbonItem, ...]) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        for item in items:
            button = RibbonButton(item)
            button.clicked.connect(
                lambda _=False, a=item.action: self.action_triggered.emit(a)
            )
            self.buttons[item.action] = button
            layout.addWidget(button)
        layout.addStretch(1)
        return page

    def button(self, action: str) -> RibbonButton | None:
        """The button for a VB control-name id, if present."""
        return self.buttons.get(action)

    def set_enabled(self, action: str, enabled: bool) -> None:
        """Enable/disable a ribbon button by id (VB per-button ``.Enabled``)."""
        button = self.buttons.get(action)
        if button is not None:
            button.setEnabled(enabled)
