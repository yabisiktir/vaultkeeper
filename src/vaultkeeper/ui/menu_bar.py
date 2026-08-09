"""NitMenuBar — the main menu bar, faithful to the VB ``MsMenu``.

Ported from ``NIT.Designer.vb`` (``NIT.Menu.vb`` regions). Reproduces the nine top
menus (File, Edit, View, Manage, Tools, Run, Web, Options, Help) with the original
item order, captions (``&`` mnemonics preserved), icons, separators and the
check-on-click toggles. Every item carries its VB control-name id (``MsInstall`` …)
and triggering emits :attr:`NitMenuBar.action_triggered` so the controller wires
handlers 1:1 with the VB ``Handles`` subs. The Web menu is populated at runtime from
the user's web links (empty here until Phase 6).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QMenuBar, QWidget

from vaultkeeper.ui import resources as R


@dataclass(frozen=True)
class MenuItem:
    """One menu item: VB control-name id, caption, image resource, checkable flag."""

    action: str
    caption: str
    image: str
    checkable: bool = False


#: A separator sentinel between menu items.
SEP = MenuItem("", "", "", False)


MENUS: tuple = (
    (
        "&File",
        "MsFile",
        (
            MenuItem("MsLoadProfile", "&Load Profile", "Profiles", False),
            MenuItem("MsOpen", "&Open", "Folder_6221", False),
            MenuItem("MsDownloadProject", "Do&wnload Project", "DownloadProject_16x", False),
            MenuItem("MsAddFiles", "Add &Files to Mod", "MoveToFolderHS", False),
            MenuItem("MsAddMods", "&Add Mods from Files", "AddModFiles", False),
            SEP,
            MenuItem("MsUpdateDownloads", "Move to &Downloads", "DownloadFolder_16x", False),
            MenuItem("MsMoveToFolder", "&Move to Folder", "FileCopy16", False),
            MenuItem("MsMoveToHistory", "Move to &History", "FileHistory", False),
            MenuItem("MsMoveToDev", "Move to Development", "DeveloperMode_16x", False),
            SEP,
            MenuItem("MsNewFolder", "&New Folder", "AddFolder", False),
            MenuItem("MsNewTextFile", "New &Text File", "NotePad", False),
            MenuItem("MsNewRtfFile", "Ne&w RTF File", "WordPad", False),
            SEP,
            MenuItem("MsBackupData", "&Backup Data", "ExportData_16x", False),
            MenuItem("MsRestoreData", "&Restore Data", "WriteToDatabase_16x", False),
            MenuItem("MsExportMods", "&Export Mods", "Export_Arrow", False),
            MenuItem("MsImportMods", "&Import Mods", "Arrow_ImportOrLoad_16x_color", False),
            SEP,
            MenuItem("MsOpenSharedStore", "Open Shared NIT Store", "NIT_Icon_v5_006c", False),
            MenuItem("MsConnect", "Connect to Shared NIT Store", "Connect_16x", False),
            SEP,
            MenuItem("MsExtractPortraits", "Extract Portrait Images", "ExtractMethod_6786", False),
            MenuItem("MsDisplayInfo", "Display Additional Info", "", False),
            MenuItem("MsProperties", "&Properties", "PropertiesW10", False),
            SEP,
            MenuItem("MsRestart", "Re&start", "Restart_Green_16x", False),
            MenuItem("MsExit", "E&xit", "ExitApp", False),
        ),
    ),
    (
        "&Edit",
        "MsEdit",
        (
            MenuItem("MsRecentMods", "Recent Mods", "History_16x", False),
            MenuItem("MsSelectAll", "Select &All", "SelectAll", False),
            SEP,
            MenuItem("MsCut", "Cu&t", "Cut_006", False),
            MenuItem("MsCopy", "&Copy", "CopyOffice2016", False),
            MenuItem("MsCopyName", "C&opy Name", "CopyName", False),
            MenuItem("MsPaste", "&Paste", "PasteW10", False),
            SEP,
            MenuItem("MsDelete", "&Delete", "delete_16x16", False),
            SEP,
            MenuItem("MsRename", "&Rename...", "RenameBlack", False),
            MenuItem("MsFind", "&Find...", "Search16", False),
            MenuItem("MsFindAndRename", "Find and Rename &Mods...", "FindAndReplace", False),
            MenuItem("MsGoToGroup", "&Go to Group...", "Stepout_6327", False),
            SEP,
            MenuItem(
                "MsConvertRestorer",
                "Conv&ert Restorer to Mod",
                "EntityDataModel_entity_type_16x16",
                False,
            ),
            MenuItem(
                "MsEditWebLink", "Edit &Link to Mod's Web Page", "WebInsertHyperlinkHS", False
            ),
            MenuItem("MsCopyWebLink", "Copy Mod's &Web Page Link", "CopyUrlLink_16x", False),
            MenuItem(
                "MsFindWebLink", "Find Mod's Web Page Lin&k", "DynamicWebSite_16x", False
            ),
            MenuItem(
                "MsCheckForUpdates", "Check for Mod &Updates", "DownloadProject_16x", False
            ),
            MenuItem("MsEditStartScreenPrefixes", "Edit Start Screen Prefixes", "Edit_16x", False),
        ),
    ),
    (
        "&View",
        "MsView",
        (
            MenuItem("MsCollapseAllGroups", "&Collapse All Groups", "Collapse_Menu_Image", False),
            MenuItem("MsExpandAllGroups", "&Expand All Groups", "Expand_Menu_Image", False),
            SEP,
            MenuItem("MsCharacterSummary", "C&haracter Summary", "user", False),
            MenuItem("MsModsPlayed", "Mods So&rted by Date Completed", "Time_Green_16x", False),
            MenuItem("MsConflicts", "&Mod File Conflicts", "Overridden", False),
            MenuItem("MsWorkshopViewer", "&Steam Workshop Subscriptions", "SteamViewer", False),
            SEP,
            MenuItem("MsLogFile", "Vaultkeeper &Log File", "NIT_Log_16x", False),
            MenuItem(
                "MsDisplaySettings",
                "Vaultkeeper &User Config File",
                "CSWorkerTemplateFile_16x",
                False,
            ),
            MenuItem("MsOpenRulesFile", "&Download Rules File", "Notepad__", False),
            SEP,
            MenuItem("MsNwnClientLogFile", "&NWN Client Log File", "NWN_16x", False),
            MenuItem("MsNwnEngineLogFile", "NWN Engine Log File", "LogProperty_16x", False),
            SEP,
            MenuItem("MsNWNIniFile", "N&WN Ini File", "open_folder16", False),
            MenuItem("MsNwnSettingsFile", "NWN Settings &File", "CPPMarkupXML_16x", False),
            MenuItem("MsNWNPlayerIniFile", "NWN &Player Ini File", "PlayerIniFile", False),
            SEP,
            MenuItem("MsNwnPatchIniFile", "NWN P&atch Ini File", "PatchPackage_16x", False),
            MenuItem("MsNwnToolsetIniFile", "NWN &Toolset Ini File", "ToolsetIniFile", False),
            MenuItem("MsNwnConfigIniFile", "NWN C&onfig Ini File", "ConfigIniFile", False),
            SEP,
            MenuItem("MsViewClipboard", "Clip&board", "TaskList_16x", False),
        ),
    ),
    (
        "&Manage",
        "MsManage",
        (
            MenuItem("MsNewGroup", "New &Group", "Group", False),
            MenuItem("MsMoveToGroup", "&Move to Group...", "XSDSchema_GraphRightToLeft", False),
            MenuItem("MsNewMod", "&New Mod", "EntityDataModel_entity_type_16x16", False),
            SEP,
            MenuItem("MsCreateInstaller", "&Create Installer", "FolderMapping16", False),
            MenuItem(
                "MsCreateMissingInstallers",
                "Create Mi&ssing Installers",
                "Mod_Installers_Create",
                False,
            ),
            MenuItem("MsChangeInstaller", "Chan&ge Installer Options", "EditInput_16x", False),
            MenuItem("MsCreateRestorer", "Create &Restorer", "Windows_Seven_Icon_63_003", False),
            MenuItem(
                "MsCreateOriginalRestorers", "Crea&te Original Restorers", "OriginalRestorer", False
            ),
            SEP,
            MenuItem("MsLoadscreens", "N&WN's Start Screens", "Image", False),
            MenuItem("MsHakPatchEditor", "&Hak Patch Priority", "OrderedList_16x", False),
            MenuItem("MsAliasSection", "A&lias Section (nwn.ini)", "open_folder16", False),
            SEP,
            MenuItem("MsPublishMod", "&Publish Mod", "package_16xLG", False),
            MenuItem("MsAnneal", "&Anneal", "Anneal_16x", False),
            SEP,
            MenuItem("MsRemoveIllegalModFiles", "Remove Illegal Mod &Files", "delete_16x16", False),
            MenuItem("MsRemoveErfs", "Remove &ERF Files", "Delete", False),
            MenuItem("MsRemoveLetoLogFiles", "Remove Leto Log Files", "Exclude_16x", False),
            SEP,
            MenuItem("MsSynchroniseMods", "Synchronise Mo&ds", "SynchronizeDatabase_16x", False),
            MenuItem("MsCompact", "C&ompress Mod Folder", "Overwrite", False),
            SEP,
            MenuItem("MsInstall", "&Install", "Install_Package_16x16", False),
            MenuItem("MsUninstall", "&Uninstall", "Uninstall", False),
        ),
    ),
    (
        "&Tools",
        "MsTools",
        (
            MenuItem("MsModExplorer", "Mod &Explorer", "Mod_Explorer_1", False),
            MenuItem("MsCharacterExplorer", "C&haracter Explorer", "LookupUser_16x", False),
            MenuItem("MsDocOrganiser", "Documentation &Organiser", "VBExtension_16x", False),
            SEP,
            MenuItem("MsGameSaves", "Game &Saves Manager", "GameManager16", False),
            MenuItem("MsSaveGameEditor", "Save Game &Editor", "GameManager16", False),
            MenuItem("MsBackupManager", "&Backup and Export Manager", "DataCompare_16x", False),
            MenuItem("MsInstallationManager", "Installation &Manager", "Installed", False),
            MenuItem(
                "MsInstallationAnalyser",
                "Installation &Analyser",
                "InstallationAnalyser_16x",
                False,
            ),
            SEP,
            MenuItem("MsWizardBuilder", "Installer Wi&zard Builder", "witchcraft", False),
            MenuItem("MsDependencyManager", "Dependenc&y Manager", "DependencyGraph_16x", False),
            MenuItem("MsPortraitManager", "Por&trait Manager", "user", False),
            SEP,
            MenuItem("MsUpdateEeFiles", "&Update Enhanced Edition Files", "UpdateEeFiles", False),
            MenuItem("MsRefreshWorkshopFiles", "Refresh Steam &Workshop Files", "Steam", False),
            SEP,
            MenuItem("MsValidateMovieFiles", "Validate Movie &Files", "Video", False),
            MenuItem(
                "MsValidateProfileData", "&Validate Profile Data", "DatabaseProperty_16x", False
            ),
            MenuItem("MsValidateMods", "Validate &Mods", "ValidateModsV5", False),
            MenuItem(
                "MsValidateModWebLinks",
                "Validate Mod Web &Links",
                "DynamicWebSite_16x",
                False,
            ),
            MenuItem("MsValidateInstalledData", "Validate Installed &Data", "", False),
            MenuItem("MsValidate", "Validate &Neverwinter Nights", "FindinFiles_6299", False),
            SEP,
            MenuItem("MsRecoverGroups", "Recover &Groups", "GroupRecover", False),
            MenuItem("MsRecoverModProperties", "Recover Mod &Properties", "RestoreMTR_16x", False),
            MenuItem("MsRepairCrcs", "&Calculate CRCs", "CRC", False),
            MenuItem("MsRebuildDatabase", "&Rebuild Database", "screwdriver_16xLG", False),
        ),
    ),
    (
        "&Run",
        "MsRun",
        (
            MenuItem("MsPlayNeverwinterNights", "&Neverwinter Nights", "StatusRun_16x", False),
            MenuItem("MsToolset", "Neverwinter Nights &Toolset", "Hammer_Builder_16xLG", False),
            # User-defined Run-menu programs (VB MsRunSeparator + user items) are
            # appended dynamically by populate_run_menu, so no static separator here.
        ),
    ),
    ("&Web", "MsWeb", ()),
    (
        "&Options",
        "MsOptions",
        (
            MenuItem("MsBasicSettings", "&Basic Settings", "SettingsCog16", False),
            MenuItem("MsSettings", "Advanced &Settings", "SettingsCogBlue", False),
            MenuItem(
                "MsFontAndColour", "Text Size and The&me Colours", "fontandcolour_x16x", False
            ),
            SEP,
            MenuItem("MsOriginalPortraits", "Show BioWare's Portrait Ima&ges", "", True),
            MenuItem("MsNumberRecentMods", "&Number Recent Mods", "", True),
            MenuItem("MsPropertiesHeight", "Automatic &Properties Panel Height", "", True),
            SEP,
            MenuItem("MsResetWindow", "Reset &Window Layout", "Reset_16x", False),
            MenuItem("MsResetWebMenu", "Reset Web Menu Icons", "ASPNETWeb_16x", False),
            MenuItem("MsResetTaskbarIcon", "Reset Taskbar Icon", "QuickRefresh_16x", False),
            MenuItem("MsClearWaitCursors", "Cl&ear Wait Cursors", "BusyTransparent", False),
            MenuItem("MsEnableClosing", "Enable Cl&osing", "StatusOK_16x", False),
            SEP,
            MenuItem(
                "MsClearScrollInfo",
                "Clear Text Position &Information",
                "ClearDictionary_16x",
                False,
            ),
            MenuItem(
                "MsClearSelectionHistory", "Clear Selection &History", "SelectHistory_Clear", False
            ),
            MenuItem("MsClearHakPortraits", "Clear Extracted Ha&k Portraits", "user_delete", False),
            SEP,
            MenuItem("MsShowRibbon", "Show &Ribbon Interface", "", True),
            SEP,
            MenuItem("MsShowToolbar", "Show &Toolbar", "", True),
            MenuItem("MsShowText", "Show Te&xt on Toolbar", "", True),
            MenuItem("MsCustomise", "C&ustomise Toolbar", "Customiser16", False),
            SEP,
            MenuItem("MsDebugOptionsMenu", "&Debug Options Menu", "DebugIcon", False),
        ),
    ),
    (
        "&Help",
        "MsHelp",
        (
            MenuItem("MsViewHelp", "View &Help", "HelpIcon", False),
            MenuItem("MsGetStarted", "Get &Started", "Key16", False),
            MenuItem("MsFAQ", "&Frequently Asked Questions (FAQ)", "FAQ_1", False),
            MenuItem("MsWhatsNew", "&What's New?", "WhatsNew_16x", False),
            MenuItem("MsHistory", "&Version History", "History_16x", False),
            SEP,
            MenuItem(
                "MsClassesSkillsAndFeats",
                "Classes, S&kills and Feats Information",
                "Information_16xLG_color",
                False,
            ),
            SEP,
            MenuItem("MsUpdateNow", "&Update Now", "UpdateNow_16x", False),
            MenuItem("MsSendFeedback", "Send Feed&back", "SendEmail_16x", False),
            MenuItem("MsSendDiagInfo", "Send &Diagnostic Information", "Message_16x", False),
            SEP,
            MenuItem("MsAbout", "&About", "NIT_Icon_v5_006c", False),
        ),
    ),
)


#: Keyboard shortcuts, verbatim from the original's ``Keyboard Shortcuts`` help
#: topic. Every command they name was already here; none of them had a key, so
#: the topic documented a set of shortcuts the port did not have.
#:
#: Ctrl+O is deliberately absent: VB's "Open the selected folder or file with
#: its associated program" acts on the Contents pane, and binding it window-wide
#: would fire it with a mod selected and nothing to open.
SHORTCUTS: dict[str, str] = {
    "MsSelectAll": "Ctrl+A",
    "MsCopyName": "Ctrl+Alt+C",
    "MsCopy": "Ctrl+C",
    "MsCut": "Ctrl+X",
    "MsPaste": "Ctrl+V",
    "MsFind": "Ctrl+F",
    "MsNewGroup": "Ctrl+G",
    "MsNewMod": "Ctrl+M",
    "MsCreateInstaller": "Ctrl+L",
    "MsModExplorer": "Ctrl+R",
    "MsCollapseAllGroups": "Ctrl+-",
    "MsExpandAllGroups": "Ctrl++",
    "MsRename": "F2",
    "MsViewHelp": "F1",
}


class NitMenuBar(QMenuBar):
    """The main window menu bar (VB ``MsMenu``)."""

    #: Emitted with an item's VB control-name id when it is triggered.
    action_triggered = Signal(str)
    #: Emitted with ``(id, checked)`` when a checkable item toggles.
    action_toggled = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.menus: dict[str, QMenu] = {}
        self.actions_by_id: dict[str, QAction] = {}
        #: User Run-menu program actions (incl. their separator), rebuilt on populate.
        self._run_user_actions: list[QAction] = []
        for title, menu_id, items in MENUS:
            menu = self.addMenu(title)
            self.menus[menu_id] = menu
            for item in items:
                if item.action == "":
                    menu.addSeparator()
                    continue
                act = QAction(R.get_icon(item.image), item.caption, self)
                act.setCheckable(item.checkable)
                if item.checkable:
                    act.toggled.connect(
                        lambda checked, a=item.action: self.action_toggled.emit(a, checked)
                    )
                else:
                    act.triggered.connect(
                        lambda _=False, a=item.action: self.action_triggered.emit(a)
                    )
                key = SHORTCUTS.get(item.action)
                if key:
                    act.setShortcut(QKeySequence(key))
                    # The menu bar is always alive, so its actions can own the
                    # window's shortcuts; a dialog with focus still gets first
                    # refusal on the key.
                    act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
                menu.addAction(act)
                self.actions_by_id[item.action] = act

    def shortcut_actions(self) -> list[QAction]:
        """The actions carrying a keyboard shortcut, for the window to adopt."""
        return [
            act
            for action_id, act in self.actions_by_id.items()
            if action_id in SHORTCUTS
        ]

    def populate_web_menu(self, links, on_open) -> None:
        """Fill the Web menu with the user's links (VB ``SetWebMenu``).

        ``links`` is a list of ``{"text", "url"}`` dicts; ``on_open`` is called with
        a URL when its item is triggered. An empty list disables the menu.
        """
        menu = self.menus.get("MsWeb")
        if menu is None:
            return
        menu.clear()
        menu.menuAction().setVisible(bool(links))
        menu.setEnabled(bool(links))
        icon = R.get_icon("ASPNETWeb_16x")
        for link in links:
            url = link.get("url", "")
            act = QAction(icon, link.get("text", url), self)
            act.setToolTip(url)
            act.triggered.connect(lambda _=False, u=url: on_open(u))
            menu.addAction(act)

    def populate_run_menu(self, entries, on_launch) -> None:
        """Append the user's Run-menu programs after the fixed Play/Toolset items
        (VB ``SetRunMenu``).

        ``entries`` is a list of ``{"text", "path"}`` dicts; ``on_launch`` is called
        with a program path when its item is triggered. A separator is shown before
        the user items only when there are any (VB ``MsRunSeparator.Visible``); an
        empty list leaves just the fixed entries.
        """
        menu = self.menus.get("MsRun")
        if menu is None:
            return
        for act in self._run_user_actions:
            menu.removeAction(act)
        self._run_user_actions = []
        entries = [e for e in entries if e.get("text") or e.get("path")]
        if not entries:
            return
        self._run_user_actions.append(menu.addSeparator())
        icon = R.get_icon("StatusRun_16x")
        for entry in entries:
            path = entry.get("path", "")
            act = QAction(icon, entry.get("text", path), self)
            act.setToolTip(path)
            act.triggered.connect(lambda _=False, p=path: on_launch(p))
            menu.addAction(act)
            self._run_user_actions.append(act)

    def populate_recent_mods(self, names, on_select, *, numbered: bool = False) -> None:
        """Fill the Recent Mods submenu (VB ``MsRecentMods`` RecentItems manager).

        ``names`` is the recent mod names (most-recent first); ``on_select`` is called
        with a name when its entry is triggered. ``numbered`` prefixes each entry with
        its position (VB ``RecentItemImageType.Number`` vs the status-icon view). An
        empty list leaves the submenu present but disabled.
        """
        from PySide6.QtWidgets import QMenu

        act = self.actions_by_id.get("MsRecentMods")
        if act is None:
            return
        menu = act.menu()
        if menu is None:
            menu = QMenu(self)
            act.setMenu(menu)
        menu.clear()
        act.setEnabled(bool(names))
        for index, name in enumerate(names, start=1):
            caption = f"{index}. {name}" if numbered else name
            entry = QAction(caption, self)
            entry.triggered.connect(lambda _=False, n=name: on_select(n))
            menu.addAction(entry)

    def action(self, item_id: str) -> QAction | None:
        """The QAction for a VB control-name id, if present."""
        return self.actions_by_id.get(item_id)

    def set_enabled(self, item_id: str, enabled: bool) -> None:
        act = self.actions_by_id.get(item_id)
        if act is not None:
            act.setEnabled(enabled)
