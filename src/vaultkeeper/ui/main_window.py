"""Vaultkeeper main window (PySide6).

The functional three-pane manager (grouped mod tree | contents | details) wrapped in
the faithful VB NIT chrome: the seven-tab :class:`Ribbon`, the :class:`QuickToolbar`,
and the :class:`NitStatusBar`, plus the menu bar and the app icon. It is wired to a
:class:`ProfileController`, so selecting mods and choosing Install/Uninstall (from the
menu, ribbon or toolbar) drives the real domain engine. Ribbon/toolbar buttons emit
their VB control-name ids into :meth:`_on_command`, which dispatches the commands
implemented so far and reports "not available yet" for the rest.
"""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.file_view import ContentsView, FileView
from vaultkeeper.ui.menu_bar import NitMenuBar
from vaultkeeper.ui.quick_toolbar import QuickToolbar
from vaultkeeper.ui.ribbon import Ribbon
from vaultkeeper.ui.status_bar import NitStatusBar


class MainWindow(QMainWindow):
    """The Vaultkeeper main window."""

    def __init__(self, controller: ProfileController | None = None) -> None:
        super().__init__()
        self.controller = controller
        self._game_process = None  # a running NWN QProcess, when playing
        self._play_started = None
        self.setWindowTitle("Vaultkeeper")
        self.setWindowIcon(R.app_icon())
        self.resize(1000, 640)

        self._tree = FileView("Mods")
        self._tree.selection_changed.connect(self._on_selection_changed)
        self._tree.mods_dropped_on_group.connect(self._on_mods_dropped_on_group)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_mods_context_menu)

        self._contents = ContentsView()
        # Contents-pane file actions (VB CmContents): double-click views a file,
        # right-click offers View / Delete.
        self._contents_mod: str | None = None
        # Cut/Copy/Paste clipboard for Contents files: (mod, folder, filename, is_cut).
        self._file_clipboard: tuple | None = None
        self._contents.itemDoubleClicked.connect(self._on_view_contents_file)
        self._contents.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._contents.customContextMenuRequested.connect(
            self._show_contents_context_menu
        )
        self._mod_info = QLabel("")
        self._mod_info.setWordWrap(True)
        self._mod_info.setMargin(6)
        self._mod_info.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._details_list = QTreeWidget()
        self._details_list.setHeaderLabels(["Property", "Value"])
        self._details_list.setRootIsDecorated(False)
        # The properties list is read-only; the lower pane is the editable Mod Notes.
        self._details = QTextEdit()
        self._details.setPlaceholderText("Mod notes…")
        self._notes_mod: str | None = None  # the mod whose notes are loaded

        # Nested splitter layout, matching the VB ScProfile/ScMod/ScContents/ScDetails:
        #   mods | (contents / mod-info) | (details list / properties+notes)
        sc_contents = QSplitter(Qt.Orientation.Vertical)
        sc_contents.addWidget(self._contents)
        sc_contents.addWidget(self._mod_info)
        sc_contents.setStretchFactor(0, 3)
        sc_contents.setStretchFactor(1, 1)

        sc_details = QSplitter(Qt.Orientation.Vertical)
        sc_details.addWidget(self._details_list)
        sc_details.addWidget(self._details)
        sc_details.setStretchFactor(0, 2)
        sc_details.setStretchFactor(1, 3)

        sc_mod = QSplitter(Qt.Orientation.Horizontal)
        sc_mod.addWidget(sc_contents)
        sc_mod.addWidget(sc_details)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(sc_mod)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)

        # Command chrome (faithful ports of the VB ribbon/toolbar/status bar).
        self.ribbon = Ribbon()
        self.ribbon.action_triggered.connect(self._on_command)
        self.quick_toolbar = QuickToolbar()
        self.quick_toolbar.action_triggered.connect(self._on_command)
        self.addToolBar(self.quick_toolbar)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.ribbon)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self.nit_status = NitStatusBar()
        self.nit_status.mods_clicked.connect(self._on_profile_menu)
        self.setStatusBar(self.nit_status)

        self._build_menu()
        self._apply_command_availability()
        self._apply_leto_menu_visibility()
        # Idle status: the accumulated-changes summary (VB MgInfo), like
        # "Installed file and Mod changes: None."; "Ready" with no profile.
        self.nit_status.set_info(
            controller.change_status_line() if controller is not None else "Ready"
        )

        if controller is not None:
            self._install_prompter()
            self.refresh()
        else:
            self._show_empty_state()

    def _install_prompter(self) -> None:
        """Give the controller a Qt-backed GameMapper prompter for the play loop."""
        if self.controller is not None:
            from vaultkeeper.ui.prompter import QtGameMapperPrompter

            self.controller.play_prompter = QtGameMapperPrompter(self)

    def _show_empty_state(self) -> None:
        self._details.setHtml(
            "<h3>Welcome to Vaultkeeper</h3>"
            "<p>No profile is open yet.</p>"
            "<p>Use <b>File &rarr; Load Profile</b> (or <b>Open</b>) to locate your "
            "Neverwinter Nights folder and create a profile.</p>" + self._import_hint()
        )
        self.nit_status.set_info("No profile — use File ▸ Load Profile")

    @staticmethod
    def _import_hint() -> str:
        """A prompt to import an existing NIT Store, when one is detected on disk."""
        from vaultkeeper.ui.session import detect_legacy_store

        if detect_legacy_store() is None:
            return ""
        return (
            "<p>An existing <b>NIT Store</b> was found on this machine. Click "
            "<b>Mods</b> in the status bar below, then <b>Import Legacy NIT "
            "Store…</b>, to bring in your mods and their groups.</p>"
        )

    # -- Menu -------------------------------------------------------------- #
    def _build_menu(self) -> None:
        """Install the faithful VB menu bar and bind the selection-driven items."""
        self.nit_menu = NitMenuBar()
        self.setMenuBar(self.nit_menu)
        self.nit_menu.action_triggered.connect(self._on_command)
        self.nit_menu.action_toggled.connect(self._on_toggle)

        # Selection-driven items reused by the enable/disable logic.
        self._act_install = self.nit_menu.action("MsInstall")
        self._act_uninstall = self.nit_menu.action("MsUninstall")
        self._act_rename = self.nit_menu.action("MsRename")
        self._act_remove = self.nit_menu.action("MsDelete")
        self._act_properties = self.nit_menu.action("MsProperties")
        for act in (
            self._act_install,
            self._act_uninstall,
            self._act_rename,
            self._act_remove,
            self._act_properties,
        ):
            if act is not None:
                act.setEnabled(False)

        # The ribbon/toolbar visibility toggles start checked (both shown).
        for item_id in ("MsShowRibbon", "MsShowToolbar"):
            act = self.nit_menu.action(item_id)
            if act is not None:
                act.setChecked(True)

        # Populate the Web menu from the user's saved links (VB SetWebMenu).
        from vaultkeeper.config.settings import load_settings

        _settings = load_settings()
        self.nit_menu.populate_web_menu(_settings.web_links, self._open_url)
        # Populate the Run menu's user programs (VB SetRunMenu), after Play/Toolset.
        self.nit_menu.populate_run_menu(_settings.run_links, self._on_run_program)

        # Recent Mods (VB MsRecentMods): most-recently-selected mod names, capped at
        # Settings.max_recent_mods, shown in a dynamic submenu. Number Recent Mods
        # (VB MsNumberRecentMods) toggles numbering the entries.
        self._recent_mods: list[str] = []
        act = self.nit_menu.action("MsNumberRecentMods")
        if act is not None:
            act.setChecked(_settings.number_recent_mods)
        self._rebuild_recent_mods_menu()

        # Right-aligned menu-bar cluster, mirroring the VB menu strip's right side
        # (TsbModSelector + MsPlayedInfo + MsHelpContents). QMenuBar allows one
        # corner widget, so they share a container.
        from PySide6.QtWidgets import (
            QComboBox,
            QCompleter,
            QHBoxLayout,
            QToolButton,
        )

        self._menu_corner = QWidget()  # keep a ref so Qt doesn't collect it
        corner = self._menu_corner
        corner_row = QHBoxLayout(corner)
        corner_row.setContentsMargins(0, 0, 4, 0)
        corner_row.setSpacing(4)

        # Mod Selector: a type-to-find combo bound to the mod list (VB
        # TsbModSelector, SourceListView = FvMods; ItemSelected → SelectMod).
        self._mod_selector = QComboBox()
        self._mod_selector.setEditable(True)
        self._mod_selector.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._mod_selector.setMinimumWidth(220)
        self._mod_selector.setMaxVisibleItems(20)
        self._mod_selector.lineEdit().setPlaceholderText("Mod Selector")
        self._mod_selector.setToolTip("Type to find and select a mod")
        completer = self._mod_selector.completer()
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._mod_selector.activated.connect(self._on_mod_selector_activated)
        corner_row.addWidget(self._mod_selector)

        # "Mod played for …" (VB MsPlayedInfo): the selected mod's play time;
        # opens the play-data view when clicked.
        self._played_info = QToolButton()
        self._played_info.setAutoRaise(True)
        self._played_info.setText("")
        self._played_info.clicked.connect(self._on_played_info)
        corner_row.addWidget(self._played_info)

        # Help "?" quick button (VB MsHelpContents → HelpFile.Open(MsViewHelp)).
        help_btn = QToolButton()
        help_btn.setText("?")
        help_btn.setAutoRaise(True)
        help_btn.setToolTip("Help Contents")
        help_btn.clicked.connect(self._on_help_contents)
        corner_row.addWidget(help_btn)

        self.nit_menu.setCornerWidget(corner)
        self._populate_mod_selector()

        # Restore the saved window geometry (VB window-position preference).
        self._restore_geometry()

    def _populate_mod_selector(self) -> None:
        """Fill the Mod Selector combo with every mod name (VB SourceListView)."""
        if getattr(self, "_mod_selector", None) is None:
            return  # an early refresh() before the corner cluster is built
        if self.controller is None:
            self._mod_selector.clear()
            return
        names = [
            md.mod_name
            for _group, mods in self.controller.groups()
            for md in mods
            if md.is_not_group_item
        ]
        blocker = QSignalBlocker(self._mod_selector)  # don't fire activated
        self._mod_selector.clear()
        self._mod_selector.addItems(sorted(names, key=str.lower))
        self._mod_selector.setCurrentIndex(-1)
        self._mod_selector.setCurrentText("")
        del blocker

    def _on_mod_selector_activated(self, _index: int) -> None:
        """Select the chosen mod (VB TsbModSelector.ItemSelected → SelectMod)."""
        name = self._mod_selector.currentText().strip()
        if name:
            self._select_mod_by_name(name)

    def _on_played_info(self) -> None:
        """Open the play-data view (VB MsPlayedInfo.Click → PlayDataManager.View).

        Shows the pending-play-data view when there are unattributed sessions
        (VB PlayDataViewPending), otherwise the per-mod play-times report.
        """
        if self.controller is None:
            return
        if self.controller.pending_play_report()["count"] > 0:
            from vaultkeeper.ui.dialogs.play_data_view_pending import (
                PlayDataViewPending,
            )

            self._play_data_pending = PlayDataViewPending.show_for(self.controller, self)
            return
        from vaultkeeper.ui.dialogs.play_data_viewer import PlayDataViewer

        self._play_data_viewer = PlayDataViewer.show_for(self.controller, self)

    def _update_played_info(self, mod_name: str | None) -> None:
        """Refresh the right-aligned play-time menubar item for the selected mod."""
        if self.controller is None or not mod_name:
            self._played_info.setText("")
            return
        self._played_info.setText(self.controller.mod_played_info(mod_name))

    def _restore_geometry(self) -> None:
        """Restore the saved window size/position if the preference is on."""
        from vaultkeeper.config.settings import load_settings

        settings = load_settings()
        if settings.remember_window_position and settings.window_geometry:
            from PySide6.QtCore import QByteArray

            try:
                data = QByteArray.fromBase64(settings.window_geometry.encode("ascii"))
                self.restoreGeometry(data)
            except (ValueError, TypeError):
                pass

    def _save_geometry(self) -> None:
        """Persist the current window geometry if the preference is on."""
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings()
        if not settings.remember_window_position:
            return
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        if geometry != settings.window_geometry:
            settings.window_geometry = geometry
            save_settings(settings)

    def _open_url(self, url: str) -> None:
        """Open a Web-menu link in the default browser (VB WebMenu_Click)."""
        if not url:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(url))
        self.nit_status.set_info(f"Opening {url}")

    def _on_run_program(self, path: str) -> None:
        """Launch an external Run-menu program (VB ``RunMenu_Click`` 'Case Else' →
        ``RunProgram(..., UseShell)``).

        A missing program is reported (VB shows "Unable to run … because the program
        does not exist"); otherwise it is started detached in its own folder.
        """
        from pathlib import Path

        exe = Path(path) if path else None
        if exe is None or not exe.exists():
            from PySide6.QtWidgets import QMessageBox

            name = exe.name if exe is not None else "the program"
            QMessageBox.warning(
                self,
                "Run",
                f"Unable to run {name} because the program does not exist.",
            )
            return
        from PySide6.QtCore import QProcess

        if QProcess.startDetached(str(exe), [], str(exe.parent)):
            self.nit_status.set_info(f"Launched {exe.name}.")
        else:
            self.nit_status.set_info(f"Could not launch {exe.name}.")

    def _on_toggle(self, item_id: str, checked: bool) -> None:
        """Handle checkable menu items (VB check-on-click toggles)."""
        if item_id == "MsShowRibbon":
            self.ribbon.setVisible(checked)
        elif item_id == "MsShowToolbar":
            self.quick_toolbar.setVisible(checked)
        elif item_id == "MsNumberRecentMods":
            # VB MsNumberRecentMods_CheckedChanged: persist + re-render the list.
            from vaultkeeper.config.settings import load_settings, save_settings

            settings = load_settings()
            settings.number_recent_mods = checked
            save_settings(settings)
            self._rebuild_recent_mods_menu()

    # -- Recent Mods (VB MsRecentMods) ------------------------------------- #
    def _record_recent_mod(self, name: str) -> None:
        """Push a selected mod to the front of the Recent Mods list (VB Manager.Add)."""
        from vaultkeeper.config.settings import load_settings

        if not name:
            return
        recent = [n for n in self._recent_mods if n != name]
        recent.insert(0, name)
        max_recent = max(1, load_settings().max_recent_mods)
        self._recent_mods = recent[:max_recent]
        self._rebuild_recent_mods_menu()

    def _rebuild_recent_mods_menu(self) -> None:
        """Re-render the Recent Mods submenu from the tracked list."""
        from vaultkeeper.config.settings import load_settings

        # Drop names no longer in the profile (VB Manager.Remove on delete/rename).
        if self.controller is not None:
            self._recent_mods = [
                n for n in self._recent_mods if self.controller.pd.mod_item(n) is not None
            ]
        self.nit_menu.populate_recent_mods(
            self._recent_mods,
            self._select_mod_by_name,
            numbered=load_settings().number_recent_mods,
        )

    def set_controller(self, controller: ProfileController) -> None:
        """Swap in a new active profile controller and repopulate."""
        self.controller = controller
        self._install_prompter()
        self.refresh()
        self._notify_config_drift()

    def _notify_config_drift(self) -> None:
        """Non-modal notice if the game's config changed since we last saw it."""
        if self.controller is None:
            return
        changes = self.controller.startup_config_check()
        if changes:
            names = ", ".join(sorted({c.path.name for c in changes}))
            self.nit_status.set_info(f"Note: game config changed ({names})")

    def _on_setup(self) -> None:
        """First-run flow: locate the NWN folder, name a profile, open it."""
        nwn_dir = QFileDialog.getExistingDirectory(self, "Locate your Neverwinter Nights folder")
        if not nwn_dir:
            return
        name, ok = QInputDialog.getText(self, "Profile", "Profile name:", text="My Mods")
        if not ok or not name.strip():
            return
        from vaultkeeper.ui.session import configure_profile

        try:
            controller = configure_profile(nwn_dir, name.strip())
        except OSError as exc:
            QMessageBox.warning(self, "Set Up Profile", f"Could not create the profile:\n{exc}")
            return
        self.set_controller(controller)
        self.nit_status.set_info(f"Profile '{name.strip()}' ready")

    # -- Profile switching ------------------------------------------------- #
    def _on_profile_menu(self) -> None:
        """Show the profile selector (VB BtMods) and switch on choice."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu

        from vaultkeeper.config.settings import load_settings
        from vaultkeeper.ui.session import list_profiles

        profiles = list_profiles()
        active = load_settings().active_profile
        menu = QMenu(self)
        for name in profiles:
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(name == active)
            act.triggered.connect(lambda _=False, n=name: self._switch_profile(n))
        if profiles:
            menu.addSeparator()
        menu.addAction("New Profile…", self._on_setup)
        menu.addAction("Import Legacy NIT Store…", self._on_import_legacy)
        menu.exec(QCursor.pos())

    def offer_legacy_import(self) -> None:
        """On first run, offer to import a detected legacy NIT Store (VB auto-migrates).

        Only prompts when a legacy store is present *and* the (freshly auto-created)
        active profile has no mods yet — so it never nags an established user. Choosing
        *Yes* opens the import dialog; *No* leaves the empty profile with the standing
        "import an existing collection" hint.
        """
        from vaultkeeper.ui.session import detect_legacy_store

        if self.controller is None or detect_legacy_store() is None:
            return
        total, _ = self.controller.counts()
        if total > 0:
            return
        from PySide6.QtWidgets import QMessageBox

        answer = QMessageBox.question(
            self,
            "Import Legacy NIT Store",
            "An existing NIT Store was found on this machine.\n\n"
            "Import your mods and their groups now?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._on_import_legacy()

    def _on_import_legacy(self) -> None:
        """Migrate a legacy NIT Store profile into Vaultkeeper (port addition)."""
        from vaultkeeper.ui.dialogs.import_legacy import ImportLegacyStore

        self._import_legacy = ImportLegacyStore.show_for(
            self, on_imported=self._switch_profile
        )

    def _switch_profile(self, name: str) -> None:
        from vaultkeeper.ui.session import switch_profile

        controller = switch_profile(name)
        if controller is not None:
            self.set_controller(controller)
            self.nit_status.set_info(f"Switched to profile '{name}'")

    # -- Population -------------------------------------------------------- #
    def refresh(self) -> None:
        """Rebuild the mod tree from the controller's profile."""
        if self.controller is None:
            self._tree.clear()
            return
        self._tree.populate(self.controller.groups())
        self._populate_mod_selector()
        self._update_status()
        self._update_title()
        total, _ = self.controller.counts()
        if total == 0:
            self._details.setHtml(
                "<h3>This profile has no mods yet</h3>"
                "<p>Add mods with <b>Mods &rarr; New Mod</b>, or import an existing "
                "collection.</p>" + self._import_hint()
            )

    def _update_status(self) -> None:
        if self.controller is None:
            return
        total, installed = self.controller.counts()
        # Real status segments (VB BtModCount) instead of an overlaying message.
        self.nit_status.set_mod_count(installed, total)

    # -- Selection / actions ---------------------------------------------- #
    def selected_mod_names(self) -> list[str]:
        return self._tree.selected_mod_names()

    #: The mod list's right-click menu (VB CmMods, NIT.Menu.vb DefineContextMenus);
    #: None is a separator. Items reuse the menu-bar actions of the same id.
    _MODS_CONTEXT_ITEMS = (
        "MsRecentMods", "MsSelectAll", None,
        "MsCut", "MsCopy", "MsCopyName", "MsPaste", "MsRename", None,
        "MsDelete", None,
        "MsNewGroup", "MsNewMod", "MsAddFiles", None,
        "MsCreateInstaller", "MsCreateRestorer", None,
        "MsInstall", "MsUninstall", "MsPublishMod", "MsExportMods", None,
        "MsGoToGroup", "MsMoveToGroup", None,
        "MsProperties",
    )

    def _build_mods_context_menu(self):
        """Build the mod-list context menu, reusing the menu-bar actions (CmMods)."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        pending_separator = False
        for item in self._MODS_CONTEXT_ITEMS:
            if item is None:
                pending_separator = menu.actions() != []
                continue
            action = self.nit_menu.action(item)
            if action is None:
                continue
            if pending_separator:
                menu.addSeparator()
                pending_separator = False
            menu.addAction(action)
        return menu

    def _show_mods_context_menu(self, pos) -> None:
        if self.controller is None:
            return
        menu = self._build_mods_context_menu()
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _on_mods_dropped_on_group(self, names: list[str], group: str) -> None:
        """Move dragged mods into the group they were dropped on (VB drag-drop)."""
        if self.controller is None or not names:
            return
        # No-op if every dragged mod is already in the target group.
        current = {
            self.controller.pd.mod_item(n).group
            for n in names
            if self.controller.pd.mod_item(n) is not None
        }
        if current == {group}:
            return
        self.controller.move_to_group(names, group)
        self.refresh()
        label = group if not group.startswith("......") else "No Group"
        self.nit_status.set_info(f"Moved {len(names)} mod(s) to '{label}'")

    def _set_install_availability(self, names: list[str]) -> None:
        """Set Install/Uninstall availability + the Play-tab combined button's
        caption, icon and visibility from the current selection.

        Faithful to VB ``NIT.ModView.SetInstallAvailability``: exactly one of
        Install/Uninstall is enabled per the selected mod's installer + installed
        state (never both), the caption reads "Install/Uninstall Selected Mod(s)"
        and the ribbon button + its toolbar twins hide when neither applies.
        """
        install_enabled = False
        uninstall_enabled = False
        ribbon_text = "Selected Mod"
        pd = self.controller.pd if self.controller is not None else None
        mods = [] if pd is None else [pd.mod_item(n) for n in names]
        mods = [m for m in mods if m is not None]
        if len(mods) == 1:
            md = mods[0]
            # HasModInstaller ⟺ the state machine left it out of State.NONE.
            if md.is_not_group_item and md.mod_state != State.NONE:
                uninstall_enabled = md.installed
                install_enabled = not uninstall_enabled
        elif len(mods) > 1:
            ribbon_text = "Selected Mods"
            has_installer = any(m.mod_state != State.NONE for m in mods)
            can_install = any(m.is_not_group_item and not m.installed for m in mods)
            if has_installer:
                install_enabled = can_install
                uninstall_enabled = not can_install

        self._act_install.setEnabled(install_enabled)
        self._act_uninstall.setEnabled(uninstall_enabled)
        # Toolbar twins: show the applicable one (VB qat.ToolItem(...).Visible).
        self.quick_toolbar.set_visible(
            "TsInstall", install_enabled or not uninstall_enabled
        )
        self.quick_toolbar.set_visible("TsUninstall", uninstall_enabled)
        # Play-tab combined button (VB RbnInstallUninstall): caption/icon/visibility.
        button = self.ribbon.button("RbnInstallUninstall")
        if button is not None:
            button.setVisible(install_enabled or uninstall_enabled)
            if install_enabled:
                button.setText(f"Install\n{ribbon_text}")
                button.setIcon(R.get_icon("Install_Package_32x32"))
            elif uninstall_enabled:
                button.setText(f"Uninstall\n{ribbon_text}")
                button.setIcon(R.get_icon("Uninstall_Package_32x32"))

    def _update_group_status(self, names: list[str]) -> None:
        """Show the selected mods' shared group + installed/total count in the
        status bar (VB NitUserInterface.DisplayGroupModCounts).

        Blank ("None") when the selection is empty or spans more than one group;
        a hidden group (No Group / Installed by NWN) reads "None (i/t)" like VB.
        """
        if self.controller is None:
            self.nit_status.set_group("None")
            return
        selected_group: str | None = None
        for name in names:
            md = self.controller.pd.mod_item(name)
            if md is None or md.is_group_item:
                continue
            if selected_group is None:
                selected_group = md.group
            elif selected_group != md.group:
                selected_group = None
                break
        if selected_group is None:
            self.nit_status.set_group("None")
            return
        installed = total = 0
        for group, mods in self.controller.groups():
            if group == selected_group:
                for m in mods:
                    if m.is_not_group_item:
                        total += 1
                        installed += 1 if m.installed else 0
                break
        from vaultkeeper.core import constants as C

        hidden = selected_group in (C.GROUP_INSTALLED, C.GROUP_NONE)
        display = "None" if hidden else selected_group
        self.nit_status.set_group(f"{display} ({installed:,}/{total:,})")

    def _update_title(self) -> None:
        """Title bar = "Vaultkeeper — <played mod> (<save location>)" (VB TitleInfo).

        The mod currently being played and the in-module location both come from
        the current game save (the CHM labels these zones "Mod currently being
        played" / "Location within the Mod being played"), so — unlike a mod-list
        selection — this reflects game state and updates on refresh. Falls back to
        "Vaultkeeper" when nothing has been saved.
        """
        mod = location = ""
        if self.controller is not None:
            mod, location = self.controller.current_play_title()
        if mod and location:
            self.setWindowTitle(f"Vaultkeeper — {mod} ({location})")
        elif mod:
            self.setWindowTitle(f"Vaultkeeper — {mod}")
        else:
            self.setWindowTitle("Vaultkeeper")

    def _on_selection_changed(self, names: list[str] | None = None) -> None:
        if names is None:
            names = self.selected_mod_names()
        has_sel = bool(names)
        self._set_install_availability(names)
        self._update_group_status(names)
        self._act_remove.setEnabled(has_sel)
        self._act_rename.setEnabled(len(names) == 1)  # rename one at a time
        if self._act_properties is not None:
            self._act_properties.setEnabled(len(names) == 1)
        if self.controller is not None and len(names) == 1:
            md = self.controller.pd.mod_item(names[0])
            if md is not None:
                self._show_details(md)
                self._show_contents(md)
                # Track the selected mod in the Recent Mods list (VB Manager.Add).
                self._record_recent_mod(names[0])
            self._update_played_info(names[0])
        else:
            self._save_current_notes()
            self._notes_mod = None
            self._contents.clear()
            self._contents_mod = None
            self._details_list.clear()
            self._details.clear()
            self._mod_info.setText("")
            self._update_played_info(None)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist any unsaved mod notes + the window geometry before closing."""
        self._save_current_notes()
        self._save_geometry()
        super().closeEvent(event)

    def _show_contents(self, md: ModData) -> None:
        """Show the selected mod's files, grouped by folder, with install state."""
        if self.controller is None:
            self._contents.clear()
            self._contents_mod = None
            return
        self._contents_mod = md.mod_name
        self._contents.populate(self.controller.mod_contents_report(md.mod_name))

    def _show_contents_context_menu(self, pos) -> None:
        """Right-click a Contents file to View or Delete it (VB CmContents)."""
        if self.controller is None or self._contents_mod is None:
            return
        if self._contents.selected_file() is None:  # a folder row / nothing selected
            return
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("View File", self._on_view_contents_file)
        menu.addAction("Display Info", self._on_display_contents_info)
        menu.addAction("Copy Name", self._on_copy_contents_name)
        menu.addSeparator()
        menu.addAction("Cut", lambda: self._on_copy_contents_file(cut=True))
        menu.addAction("Copy", lambda: self._on_copy_contents_file(cut=False))
        paste = menu.addAction("Paste", self._on_paste_contents_file)
        paste.setEnabled(self._file_clipboard is not None)
        menu.addSeparator()
        menu.addAction("Delete File", self._on_delete_contents_file)
        menu.exec(self._contents.viewport().mapToGlobal(pos))

    def _on_copy_contents_file(self, *, cut: bool) -> None:
        """Put the selected Contents file on the clipboard (VB CmContents Cut/Copy)."""
        selected = self._contents.selected_file()
        if selected is None or self._contents_mod is None:
            return
        folder, filename = selected
        self._file_clipboard = (self._contents_mod, folder, filename, cut)
        self.nit_status.set_info(f"{'Cut' if cut else 'Copied'} {filename}.")

    def _on_paste_contents_file(self) -> None:
        """Paste the clipboard file into the selected mod (VB CmContents Paste)."""
        if (
            self.controller is None
            or self._contents_mod is None
            or self._file_clipboard is None
        ):
            return
        dest_mod = self._contents_mod  # refresh() clears the selection, so capture it
        src_mod, folder, filename, cut = self._file_clipboard
        ok = self.controller.copy_mod_file(src_mod, folder, filename, dest_mod, move=cut)
        if not ok:
            self.nit_status.set_info(f"Could not paste {filename}.")
            return
        if cut:
            self._file_clipboard = None  # a cut file is consumed by the paste
        self.refresh()
        md = self.controller.pd.mod_item(dest_mod)
        if md is not None:
            self._show_contents(md)
        self.nit_status.set_info(f"Pasted {filename} into {dest_mod}.")

    def _on_display_contents_info(self, *_args) -> None:
        """Preview the selected Contents file (VB ``MsDisplayInfo``).

        A ``.bic`` opens the Character Explorer summary; an image (loadscreen /
        portrait / texture) opens the image viewer; anything else falls back to the
        read-only text viewer.
        """
        if self.controller is None or self._contents_mod is None:
            return
        selected = self._contents.selected_file()
        if selected is None:
            return
        folder, filename = selected
        path = self.controller.mod_file_path(self._contents_mod, folder, filename)
        if path is None:
            self.nit_status.set_info(f"{filename} is not on disk.")
            return
        from vaultkeeper.ui.dialogs.image_viewer import IMAGE_EXTENSIONS, ImageViewer

        ext = path.suffix.lower()
        # VB BehaviourDisplayImageFiles: when off, images open as text, not a preview.
        show_images = self.controller._settings().display_image_files
        if ext == ".bic":
            self._show_character_file(path)
        elif ext in IMAGE_EXTENSIONS and show_images:
            self._image_viewer = ImageViewer.show_for(path, self)
        else:
            self._on_view_contents_file()

    def _show_character_file(self, path) -> None:
        """Open the Character Explorer summary for a single ``.bic`` file."""
        from vaultkeeper.core.formats.bic_reader import BicFileReader
        from vaultkeeper.game.character import CharacterFile
        from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer

        info = BicFileReader().read_file(path)
        if info is None:
            self.nit_status.set_info(f"Unable to read {path.name}.")
            return
        cf = CharacterFile(path=path, info=info)

        def resolver(resref, own_folder):
            return self.controller.portrait_path(resref, extra_dirs=[own_folder])

        self._character_viewer = CharacterViewer(
            [cf],
            resolver,
            self,
            portrait_size=self.controller._settings().portrait_display_size,
        )
        self._character_viewer.show()

    def _on_copy_contents_name(self) -> None:
        """Copy the selected Contents file's name to the clipboard (VB CmContents CopyName)."""
        selected = self._contents.selected_file()
        if selected is None:
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(selected[1])  # (folder, filename)
        self.nit_status.set_info(f"Copied {selected[1]}.")

    def _on_view_contents_file(self, *_args) -> None:
        """Open the selected Contents file in the read-only viewer (VB CmContents Open)."""
        if self.controller is None or self._contents_mod is None:
            return
        selected = self._contents.selected_file()
        if selected is None:
            return
        folder, filename = selected
        path = self.controller.mod_file_path(self._contents_mod, folder, filename)
        if path is None:
            self.nit_status.set_info(f"{filename} is not on disk.")
            return
        from vaultkeeper.ui.dialogs.text_viewer import TextViewer

        self._text_viewer = TextViewer.show_file(path, filename, self)

    def _on_delete_contents_file(self) -> None:
        """Delete the selected Contents file from the mod (VB CmContents Delete)."""
        if self.controller is None or self._contents_mod is None:
            return
        selected = self._contents.selected_file()
        if selected is None:
            return
        folder, filename = selected
        if not self._confirm("Delete File", f"Delete '{filename}' from {self._contents_mod}?"):
            return
        if self.controller.delete_mod_file(self._contents_mod, folder, filename):
            md = self.controller.pd.mod_item(self._contents_mod)
            if md is not None:
                self._show_contents(md)
                self._show_details(md)
            self.refresh()
            self.nit_status.set_info(f"Deleted {filename}.")

    def _show_details(self, md: ModData) -> None:
        # Details list (VB FvDetails): key properties as Property/Value rows.
        group = self.controller.group_label(md.group) if self.controller else md.group
        rows: list[tuple[str, str]] = [
            ("Group", group),
            ("State", md.mod_state.name.replace("_", " ").title()),
            ("Rating", md.rating.name.title()),
            ("Files", f"{len(md.files):,}"),
            ("Dependencies", f"{len(md.dependencies):,}"),
            ("Completed", f"{md.completed_count:,} time(s)"),
        ]
        if md.best_weapon.name != "NONE":
            rows.append(("Best weapon", md.best_weapon.name.replace("_", " ").title()))
        self._details_list.clear()
        for prop, value in rows:
            self._details_list.addTopLevelItem(QTreeWidgetItem([prop, value]))
        self._details_list.resizeColumnToContents(0)

        # Mod info (VB TlModInfoContainer): a short summary line.
        state = md.mod_state.name.replace("_", " ").title()
        play = ""
        if self.controller is not None:
            loop = self.controller.play_loop
            if loop is not None:
                played = loop.play_time(md.mod_name)
                if played.total_seconds() > 0:
                    play = f" · played {loop.play_data.format_time(played, '')}"
        if md.web_link:
            play = f"{play}  ·  {md.web_link}" if play else f"  ·  {md.web_link}"
        self._mod_info.setText(f"{md.mod_name} — {state}{play}")

        # Editable Mod Notes (VB per-mod .rtf). Persist the previously-shown mod first.
        self._save_current_notes()
        self._notes_mod = md.mod_name
        if self.controller is not None:
            self._details.setPlainText(self.controller.read_notes(md.mod_name))
        self._details.document().setModified(False)

    def _save_current_notes(self) -> None:
        """Persist the currently-loaded mod's notes if the user edited them.

        Honours the confirm-saves preference (VB ``RttDetails.SaveChangesPrompt`` =
        ``BehaviourConfirmSaves``): when on, ask before saving the edited notes — a
        *No* discards them; when off, the notes are saved silently.
        """
        if (
            self.controller is None
            or self._notes_mod is None
            or not self._details.document().isModified()
        ):
            return
        if self.controller._settings().confirm_saves and not self._confirm_save_notes(
            self._notes_mod
        ):
            # The user declined: discard the edit rather than save it.
            self._details.document().setModified(False)
            return
        self.controller.save_notes(self._notes_mod, self._details.toPlainText())
        self._details.document().setModified(False)

    def _confirm_save_notes(self, mod_name: str) -> bool:
        """Ask whether to save edited mod notes (VB BehaviourConfirmSaves). True = save."""
        return (
            QMessageBox.question(
                self, "Save Notes", f"Save changes to the notes for '{mod_name}'?"
            )
            == QMessageBox.StandardButton.Yes
        )

    # -- Ribbon / toolbar dispatch ----------------------------------------- #
    def _on_command(self, action: str) -> None:
        """Route a ribbon/toolbar action id to its handler (VB Handles subs)."""
        handler = self._command_handlers().get(action, self._not_implemented)
        handler()

    def implemented_commands(self) -> set[str]:
        """Every command id with a real handler (dispatch + checkable toggles).

        The single source of truth for the availability pass: menu/ribbon/toolbar
        items whose id is not in this set are shown disabled instead of raising
        "not available yet" when clicked.
        """
        return set(self._command_handlers()) | {
            "MsShowRibbon",
            "MsShowToolbar",
            # Recent Mods is a dynamic submenu container; Number Recent Mods is a
            # checkable toggle — both handled outside the dispatch dict.
            "MsRecentMods",
            "MsNumberRecentMods",
        }

    def _apply_command_availability(self) -> None:
        """Grey out chrome items whose command isn't implemented yet.

        The menu/ribbon/toolbar structure is a faithful mirror of the VB designer,
        so unported items stay visible for parity — but disabled, so the user can
        see at a glance what Vaultkeeper doesn't do yet. Implemented ids are left
        untouched (selection-driven enabling owns those).
        """
        implemented = self.implemented_commands()
        note = "Not yet available in Vaultkeeper."
        for item_id, act in self.nit_menu.actions_by_id.items():
            if item_id not in implemented:
                act.setEnabled(False)
                act.setToolTip(note)
        for item_id, button in self.ribbon.buttons.items():
            if item_id not in implemented:
                button.setEnabled(False)
                button.setToolTip(note)
        for item_id, act in self.quick_toolbar.actions_by_id.items():
            if item_id not in implemented:
                act.setEnabled(False)
                act.setToolTip(note)

    def _command_handlers(self) -> dict:
        """The command-id -> handler map (VB Handles subs), built per dispatch."""
        return {
            # Install / uninstall (ribbon, toolbar, menu).
            "TsInstall": self._on_install,
            "RbnInstallUninstall": self._on_install,
            "MsInstall": self._on_install,
            "TsUninstall": self._on_uninstall,
            "MsUninstall": self._on_uninstall,
            # Rename / remove.
            "TsRename": self._on_rename,
            "MsRename": self._on_rename,
            # Edit mod metadata (rating / weapon / levels / henchmen).
            "MsProperties": self._on_properties,
            # Web link (edit / copy to clipboard).
            "MsEditWebLink": self._on_edit_web_link,
            "MsCopyWebLink": self._on_copy_web_link,
            # Copy the selected mod name(s) to the clipboard.
            "MsCopyName": self._on_copy_name,
            "TsCopyName": self._on_copy_name,
            # Find files across the profile.
            "MsFind": self._on_find,
            "TsFind": self._on_find,
            # Jump the mod list to a chosen group.
            "MsGoToGroup": self._on_go_to_group,
            "TsGoToGroup": self._on_go_to_group,
            # Display info for the selected Contents file (character / image).
            "MsDisplayInfo": self._on_display_contents_info,
            "TsDelete": self._on_remove,
            "MsDelete": self._on_remove,
            # Cleanup.
            "MsRemoveErfs": lambda: self._remove_files("remove_erf_files", "ERF file"),
            # Remove Leto log files across the whole profile + game folders (VB
            # MsRemoveLetoLogFiles_Click runs the global RemoveLetoLogFiles worker).
            "MsRemoveLetoLogFiles": self._on_remove_all_leto_logs,
            # Mods-pane clipboard: copy/cut selected mods to the clipboard, paste
            # dropped folders/archives back as new mods (VB MsCut/MsCopy/MsPaste).
            "MsCopy": self._on_mods_copy,
            "MsCut": self._on_mods_copy,
            "TsCopy": self._on_mods_copy,
            "TsCut": self._on_mods_copy,
            "MsPaste": self._on_mods_paste,
            "TsPaste": self._on_mods_paste,
            # Add mods from archive files (create + extract each).
            "MsAddMods": self._on_add_mods,
            # Add files.
            "MsAddFiles": self._on_add_files,
            "TsAddFiles": self._on_add_files,
            "RbnAddFiles": self._on_add_files,
            # Move compressed files to each mod's _Downloads folder.
            "MsUpdateDownloads": self._on_update_downloads,
            "TsUpdateDownloads": self._on_update_downloads,
            "RbnUpdateDownloads": self._on_update_downloads,
            # Compress / uncompress mod folder (NTFS; Windows-only).
            "MsCompact": self._on_compact,
            # Publish a mod as a distributable archive.
            "MsPublishMod": self._on_publish_mod,
            # Mod creation.
            "MsNewMod": self._on_new_mod,
            "TsNewMod": self._on_new_mod,
            "RbnNewMod": self._on_new_mod,
            "MsCreateInstaller": self._on_create_installer,
            "TsCreateInstaller": self._on_create_installer,
            "RbnCreateInstaller": self._on_create_installer,
            "RbnBuildInstaller": self._on_create_installer,
            "RbnReCreateInstaller": self._on_create_installer,
            "MsCreateMissingInstallers": self._on_create_missing_installers,
            # Change Installer just re-runs Create Installer (VB delegates to it).
            "MsChangeInstaller": self._on_create_installer,
            "RbnChangeInstaller": self._on_create_installer,
            "MsRemoveIllegalModFiles": self._on_remove_illegal_files,
            "MsCreateRestorer": self._on_create_restorer,
            "TsCreateRestorer": self._on_create_restorer,
            "RbnCreateRestorer": self._on_create_restorer,
            # Convert a Restorer back into an installable Mod.
            "MsConvertRestorer": self._on_convert_restorer,
            # Groups.
            "MsNewGroup": self._on_new_group,
            "TsNewGroup": self._on_new_group,
            "MsMoveToGroup": self._on_move_to_group,
            "TsMoveToGroup": self._on_move_to_group,
            # Engine maintenance.
            "MsAnneal": self._on_anneal,
            "MsValidateProfileData": lambda: self._maintenance("validate_profile_data"),
            "MsRepairCrcs": lambda: self._maintenance("calculate_crcs"),
            "MsRebuildDatabase": lambda: self._maintenance("rebuild_database"),
            "MsValidateMods": lambda: self._maintenance("validate_mods"),
            "MsValidateMovieFiles": self._on_validate_movie_files,
            "MsExtractPortraits": self._on_extract_portraits,
            "MsClearHakPortraits": self._on_clear_hak_portraits,
            # Recover group / mod-property data from another profile or backup.
            "MsRecoverGroups": self._on_recover_groups,
            "MsRecoverModProperties": self._on_recover_properties,
            # Characters.
            "MsCharacterExplorer": self._on_characters,
            "RbnCharacterExplorer": self._on_characters,
            "MsCharacterSummary": self._on_characters,
            "BtCharacter": self._on_characters,
            "MsPortraitManager": self._on_portraits,
            "MsClassesSkillsAndFeats": self._on_classes_skills_feats,
            "MsLoadscreens": self._on_loadscreens,
            "MsEditStartScreenPrefixes": self._on_edit_start_screen_prefixes,
            "RbnPortraitManager": self._on_portraits,
            # Edit the GameMapper's remembered user responses.
            "DbGameMapUserReport": self._on_user_responses,
            # Play loop.
            "MsGameSaves": self._on_game_saves,
            "TsGameSaves": self._on_game_saves,
            "RbnGameSaves": self._on_game_saves,
            "MsPlayNeverwinterNights": self._on_play,
            "TsPlayNeverwinterNights": self._on_play,
            "RbnPlay": self._on_play,
            "MsToolset": lambda: self._on_play(toolset=True),
            "RbnToolset": lambda: self._on_play(toolset=True),
            "MsModsPlayed": self._on_mods_played,
            "MsWorkshopViewer": self._on_workshop,
            "MsDocOrganiser": self._on_doc_organiser,
            "RbnDocOrganise": self._on_doc_organiser,
            "MsWizardBuilder": self._on_wizard_builder,
            "RbnWizardBuilder": self._on_wizard_builder,
            "RbnMapFiles": lambda: self._on_folder_mapping("Map Files"),
            "RbnMapFolders": lambda: self._on_folder_mapping("Map Folders"),
            "MsConflicts": self._on_conflicts,
            "MsDependencyManager": self._on_dependencies,
            "RbnDependencyManager": self._on_dependencies,
            "MsInstallationAnalyser": self._on_analyse,
            "MsInstallationManager": self._on_installation_manager,
            "RbnInstallationManager": self._on_installation_manager,
            "MsHakPatchEditor": self._on_hak_patch_editor,
            "MsAliasSection": self._on_alias_section,
            "MsCreateOriginalRestorers": self._on_create_original_restorers,
            "MsModExplorer": self._on_mod_explorer,
            "RbnModExplorer": self._on_mod_explorer,
            "TsModExplorer": self._on_mod_explorer,
            # Backup / restore.
            "MsBackupData": self._on_backup_data,
            "RbnBackupData": self._on_backup_data,
            "MsRestoreData": self._on_restore_data,
            "RbnRestoreData": self._on_restore_data,
            # Downloads (Vault).
            "MsDownloadProject": self._on_download_project,
            "RbnDownloadProject": self._on_download_project,
            "TsDownloadProject": self._on_download_project,
            # Settings. VB has two surfaces: BasicSettings (a curated behaviour/UI
            # preferences dialog, whose Advanced button chains into the full
            # Settings) and the full Settings browser. The port's tabbed dialog
            # covers both, so Basic opens on the Behaviour tab, Advanced on General.
            "MsSettings": self._on_settings,
            "MsBasicSettings": lambda: self._on_settings(start_tab="Behaviour"),
            "RbnAdvancedSettings": self._on_settings,
            "RbnBasicSettings": lambda: self._on_settings(start_tab="Behaviour"),
            # Appearance (font size + light/dark theme) opens Settings on that tab
            # (VB Font & Colour editor; bounded port).
            "MsFontAndColour": lambda: self._on_settings(start_tab="Appearance"),
            "RbnFontAndColour": lambda: self._on_settings(start_tab="Appearance"),
            # View-menu file viewers (+ Diagnose-ribbon Rbn* variants share handlers).
            "MsLogFile": lambda: self._on_view_file("MsLogFile"),
            "RbnNitLog": lambda: self._on_view_file("MsLogFile"),
            "MsNwnClientLogFile": lambda: self._on_view_file("MsNwnClientLogFile"),
            "RbnNwnLog": lambda: self._on_view_file("MsNwnClientLogFile"),
            "MsNwnEngineLogFile": lambda: self._on_view_file("MsNwnEngineLogFile"),
            "RbnNwnEngineLog": lambda: self._on_view_file("MsNwnEngineLogFile"),
            "MsNWNIniFile": lambda: self._on_view_file("MsNWNIniFile"),
            "RbnNwnIni": lambda: self._on_view_file("MsNWNIniFile"),
            "MsNwnSettingsFile": lambda: self._on_view_file("MsNwnSettingsFile"),
            "RbnNwnSettingsFile": lambda: self._on_view_file("MsNwnSettingsFile"),
            "MsNWNPlayerIniFile": lambda: self._on_view_file("MsNWNPlayerIniFile"),
            "MsNwnPatchIniFile": lambda: self._on_view_file("MsNwnPatchIniFile"),
            "MsNwnConfigIniFile": lambda: self._on_view_file("MsNwnConfigIniFile"),
            "MsNwnToolsetIniFile": lambda: self._on_view_file("MsNwnToolsetIniFile"),
            # View / selection.
            "MsSelectAll": self._on_select_all,
            "TsSelectAll": self._on_select_all,
            "MsCollapseAllGroups": self._tree.collapseAll,
            "MsExpandAllGroups": self._tree.expandAll,
            # Help (VB HelpFileManager — control name -> <name>.htm topic).
            "MsViewHelp": self._on_help_contents,
            "MsGetStarted": lambda: self._on_help_topic("MsGetStarted"),
            "MsFAQ": lambda: self._on_help_topic("MsFAQ"),
            "MsWhatsNew": lambda: self._on_help_topic("MsWhatsNew"),
            "MsHistory": lambda: self._on_help_topic("MsHistory"),
            # About + Send Feedback (VB MsAbout / MsSendFeedback).
            "MsAbout": self._on_about,
            "MsSendFeedback": self._on_send_feedback,
            # Profile lifecycle.
            "MsLoadProfile": self._on_setup,
            "MsOpen": self._on_setup,
            "MsRestart": self.refresh,
            "MsExit": self.close,
        }

    # -- Help (VB HelpFileManager) ----------------------------------------- #
    def _on_help_contents(self) -> None:
        """Open the help window at its contents root (VB Help menu / TOC)."""
        from vaultkeeper.ui.dialogs.help_viewer import HelpViewer

        self._help_viewer = HelpViewer.show_contents(self)

    def _on_help_topic(self, control_name: str) -> None:
        """Open the help window at the topic for a control name (VB per-control help)."""
        from vaultkeeper.ui.dialogs.help_viewer import HelpViewer

        self._help_viewer = HelpViewer.show_for_control(control_name, self)

    def _on_about(self) -> None:
        """Show the About dialog (VB ``MsAbout``)."""
        from vaultkeeper.ui.dialogs.about import AboutDialog

        AboutDialog.show_dialog(self)

    def _on_send_feedback(self) -> None:
        """Open a feedback email draft (VB ``MsSendFeedback`` mailto).

        The support address is the original app's (de-obfuscated from its
        ``Application Definitions.txt``); ``mailto:`` only drafts, never sends.
        """
        from PySide6.QtCore import QUrl, QUrlQuery
        from PySide6.QtGui import QDesktopServices

        url = QUrl("mailto:surazal@lazweb.net")
        query = QUrlQuery()
        query.addQueryItem("subject", "Vaultkeeper Feedback")
        query.addQueryItem(
            "body",
            "Please provide as much information as possible "
            "(eg screenshots, Vaultkeeper Log, etc).",
        )
        url.setQuery(query)
        QDesktopServices.openUrl(url)

    def _remove_files(self, method: str, label: str) -> None:
        """Run a per-mod file-removal cleanup on the selection and report the count."""
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        removed = sum(getattr(self.controller, method)(n) for n in names)
        self.refresh()
        self.nit_status.set_info(f"Removed {removed} {label}(s).")

    def _on_remove_all_leto_logs(self) -> None:
        """Remove Leto log files across the profile + game folders (VB MsRemoveLetoLogFiles).

        Runs the global sweep (the same worker the startup auto-cleanup uses); this
        command is only offered when auto-delete is off (see
        ``_apply_leto_menu_visibility``).
        """
        if self.controller is None:
            return
        removed = self.controller.remove_all_leto_log_files()
        self.refresh()
        self.nit_status.set_info(f"Removed {removed} Leto log file(s).")

    def _apply_leto_menu_visibility(self) -> None:
        """Show the manual **Remove Leto Log Files** command only when the startup
        auto-delete is off (VB ``MsRemoveLetoLogFiles.Visible = Not
        ConfigDeleteLetoLogs``)."""
        act = self.nit_menu.actions_by_id.get("MsRemoveLetoLogFiles")
        if act is None:
            return
        if self.controller is not None:
            auto = self.controller._settings().delete_leto_logs
        else:
            from vaultkeeper.config.settings import load_settings

            auto = load_settings().delete_leto_logs
        act.setVisible(not auto)

    # -- Mods-pane clipboard (VB MsCut / MsCopy / MsPaste on FvMods) -------- #
    def _on_mods_copy(self) -> None:
        """Copy the selected mods' folders to the system clipboard (VB FileView.Copy).

        Puts each selected mod's folder on the clipboard as a file URL, so it can be
        pasted back (into another group/profile) or dropped into the OS file manager
        — faithful to VB, where Copy/Cut place the mod folders on the clipboard and
        Paste (``ModPaste``) turns dropped folders/archives into new mods.
        """
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        from PySide6.QtCore import QMimeData, QUrl
        from PySide6.QtWidgets import QApplication

        urls = [
            QUrl.fromLocalFile(str(self.controller.ctx.profile_mods_dir / name))
            for name in names
            if (self.controller.ctx.profile_mods_dir / name).is_dir()
        ]
        if not urls:
            self.nit_status.set_info("Nothing to copy.")
            return
        mime = QMimeData()
        mime.setUrls(urls)
        QApplication.clipboard().setMimeData(mime)
        self.nit_status.set_info(f"Copied {len(urls)} mod(s) to the clipboard.")

    def _on_mods_paste(self) -> None:
        """Paste clipboard mod folders / archives as new mods (VB ModPaste)."""
        if self.controller is None:
            return
        from pathlib import Path

        from PySide6.QtWidgets import QApplication

        mime = QApplication.clipboard().mimeData()
        if mime is None or not mime.hasUrls():
            self.nit_status.set_info("The clipboard has no mods to paste.")
            return
        sources = [
            Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()
        ]
        if not sources:
            self.nit_status.set_info("The clipboard has no mods to paste.")
            return
        # Paste into the selected mod's group (VB drop-target group), else No Group.
        selected = self.selected_mod_names()
        group = None
        if selected:
            md = self.controller.pd.mod_item(selected[0])
            group = md.group if md is not None else None
        result = self.controller.paste_mod_sources(sources, group)
        self.refresh()
        self.nit_status.set_info(result["message"])

    # -- Add files / mod creation handlers --------------------------------- #
    def _on_add_files(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Files to Mod")
        if not paths:
            return
        from pathlib import Path

        added = self.controller.add_files_to_mod(names[0], [Path(p) for p in paths])
        self.refresh()
        self.nit_status.set_info(f"Added {added} file(s) to {names[0]}.")

    def _on_add_mods(self) -> None:
        """Create new mods from selected archive files (VB ``MsAddMods``)."""
        if self.controller is None:
            return
        from vaultkeeper.core.archive import archive_filter

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Mods from Files", "", f"Archives ({archive_filter()})"
        )
        if not paths:
            return
        from pathlib import Path

        # New mods go into the selected mod's group (VB SelectedMod.Group).
        selected = self.selected_mod_names()
        group = None
        if selected:
            md = self.controller.pd.mod_item(selected[0])
            group = md.group if md is not None else None
        result = self.controller.add_mods_from_files([Path(p) for p in paths], group)
        self.refresh()
        self.nit_status.set_info(result["message"])

    def _on_update_downloads(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        result = self.controller.update_downloads(names)
        self.refresh()
        moved = result["files"] or "no"
        msg = f"Mods processed: {result['mods']}. Files moved: {moved}."
        if result["errors"]:
            msg += f" Errors: {result['errors']}."
        self.nit_status.set_info(msg)

    def _on_compact(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        result = self.controller.compress_mod_folders(names)
        self.refresh()
        self.nit_status.set_info(result["message"])

    def _on_publish_mod(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        from vaultkeeper.ui.dialogs.publish_mod import PublishMod

        dlg = PublishMod(self.controller, names[0], self)
        dlg.exec()
        self.refresh()

    def _on_new_mod(self) -> None:
        if self.controller is None:
            return
        name, ok = QInputDialog.getText(self, "New Mod", "Mod name:")
        if not ok or not name.strip():
            return
        if self.controller.create_mod(name.strip()):
            self.refresh()
            self.nit_status.set_info(f"Created mod '{name.strip()}'")
        else:
            self.nit_status.set_info(f"Mod '{name.strip()}' already exists")

    def _on_create_installer(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        copied = 0
        built = 0
        last_message = ""
        for name in names:
            # RunWizard: present the installer wizard's choices before building.
            choice, checked = self._run_installer_wizard(name)
            result = self.controller.build_installer_payload(
                name, wizard_choice=choice, wizard_checked=checked
            )
            if result["ok"]:
                built += 1
                copied += result["copied"]
                # Install-after-create preference (VB): auto-install the built mod.
                if self._install_after_create() and not self.controller._mod_installed(name):
                    self.controller.install([name])
            last_message = result["message"]
        self.refresh()
        if len(names) == 1:
            self.nit_status.set_info(last_message)
        else:
            self.nit_status.set_info(
                f"Built installer for {built} mod(s); {copied} file(s) copied."
            )

    def _install_after_create(self) -> bool:
        """The install-after-create preference (VB Settings behaviour)."""
        from vaultkeeper.config.settings import load_settings

        return load_settings().install_after_create

    def _run_installer_wizard(
        self, mod_name: str
    ) -> tuple[str | None, set[str] | None]:
        """Present the installer wizard's choices, if any (VB ``RunWizard`` modals).

        Returns ``(chosen_one, checked_many)`` — the SelectOne key the user picked
        (when there is more than one choice) and the set of SelectMany keys they kept.
        A mod with no run-wizard returns ``(None, None)`` (build everything).
        """
        prompt = self.controller.wizard_install_prompt(mod_name)
        if not prompt.get("run_wizard"):
            return None, None

        choice: str | None = None
        checked: set[str] | None = None
        choices = prompt.get("choices", [])
        if len(choices) > 1:
            from PySide6.QtWidgets import QInputDialog

            labels = [c["display"] for c in choices]
            picked, ok = QInputDialog.getItem(
                self, prompt["title"], prompt["select_one_text"], labels, 0, False
            )
            if ok:
                choice = next(c["key"] for c in choices if c["display"] == picked)
            else:
                choice = choices[0]["key"]

        prefs = prompt.get("preferences", [])
        if prefs:
            from vaultkeeper.ui.dialogs.wizard_prefs import WizardPreferencesDialog

            checked = WizardPreferencesDialog.ask(
                self, prompt["title"], prompt["select_many_text"], prefs
            )
        return choice, checked

    def _on_create_missing_installers(self) -> None:
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        if not self.controller.mods_missing_installer():
            self.nit_status.set_info("Missing Mod Installers created: None.")
            return
        from vaultkeeper.ui.dialogs.create_missing_installers import (
            CreateMissingInstallers,
        )

        dialog = CreateMissingInstallers(self.controller, self)
        if dialog.exec():
            self.refresh()
            self.nit_status.set_info("Missing installers processed.")

    def _on_extract_portraits(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        total = sum(
            self.controller.extract_mod_hak_portraits(n)["count"] for n in names
        )
        self.refresh()
        self.nit_status.set_info(f"Extracted {total} portrait(s) from hak files.")

    def _on_clear_hak_portraits(self) -> None:
        if self.controller is None:
            return
        self.nit_status.set_info(self.controller.clear_hak_portraits()["message"])

    def _on_validate_movie_files(self) -> None:
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        report = self.controller.movie_files_report()
        self.nit_status.set_info(report["summary"])
        if report["count"] > 0:
            from vaultkeeper.ui.dialogs.text_viewer import TextViewer

            self._movie_report = TextViewer.show_text(
                report["text"], "Invalid Movie Files", self
            )

    def _on_remove_illegal_files(self) -> None:
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        result = self.controller.remove_illegal_mod_files()
        self.refresh()
        self.nit_status.set_info(result["message"])

    def _on_create_restorer(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        made = sum(1 for n in names if self.controller.create_restorer(n))
        self.refresh()
        self.nit_status.set_info(f"Created restorer for {made} mod(s).")

    def _on_convert_restorer(self) -> None:
        """Convert the selected Restorer into an installable Mod (VB MsConvertRestorer)."""
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a restorer first.")
            return
        from PySide6.QtWidgets import QMessageBox

        name = names[0]
        md = self.controller.pd.mod_item(name)
        if md is None or md.is_group_item or not md.is_restorer():
            self.nit_status.set_info(f"{name} is not a restorer.")
            return
        confirm = QMessageBox.question(
            self,
            "Convert Restorer",
            f"Do you want to convert {name} from a Restorer to a Mod?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        result = self.controller.convert_restorer(name)
        self.refresh()
        if result == 1:
            self.nit_status.set_info(f"Converted {name} to a Mod.")
        elif result == 0:
            self.nit_status.set_info(
                "The Restorer does not contain any files to convert."
            )
        else:
            self.nit_status.set_info(f"Unable to convert {name}.")

    # -- Group / maintenance handlers -------------------------------------- #
    def _on_new_group(self) -> None:
        if self.controller is None:
            return
        name, ok = QInputDialog.getText(self, "New Group", "Group name:")
        if not ok or not name.strip():
            return
        if self.controller.create_group(name.strip()):
            self.refresh()
            self.nit_status.set_info(f"Created group '{name.strip()}'")
        else:
            self.nit_status.set_info(f"Group '{name.strip()}' already exists")

    def _on_move_to_group(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            return
        existing = self.controller.group_names()
        group, ok = QInputDialog.getItem(
            self, "Move to Group", "Target group:", existing, 0, editable=True
        )
        if not ok or not group.strip():
            return
        self.controller.move_to_group(names, group.strip())
        self.refresh()
        self.nit_status.set_info(f"Moved {len(names)} mod(s) to '{group.strip()}'")

    def _on_anneal(self) -> None:
        if self.controller is None:
            return
        message = self.controller.anneal()
        self.refresh()
        self.nit_status.set_info(message)

    def _maintenance(self, method: str) -> None:
        """Run a controller maintenance operation and report its result."""
        if self.controller is None:
            return
        message = getattr(self.controller, method)()
        self.refresh()
        self.nit_status.set_info(message)

    def _on_select_all(self) -> None:
        self._tree.selectAll()

    def _on_characters(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer

        self._character_viewer = CharacterViewer.show_for(self.controller, self)

    def _on_portraits(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager

        self._portrait_manager = PortraitManager.show_for(self.controller, self)

    def _on_classes_skills_feats(self) -> None:
        """Open the Classes/Skills/Feats reference viewer (VB MsClassesSkillsAndFeats)."""
        from vaultkeeper.ui.dialogs.classes_skills_feats import (
            ClassesSkillsAndFeatsDialog,
        )

        ClassesSkillsAndFeatsDialog.show_dialog(parent=self)

    def _on_loadscreens(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.start_screen_manager import StartScreenManager

        self._start_screen_manager = StartScreenManager.show_for(self.controller, self)

    def _on_edit_start_screen_prefixes(self) -> None:
        """Edit the Start-Screen prefix list (VB MsEditStartScreenPrefixes)."""
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.prefix_editor import PrefixEditor

        self._prefix_editor = PrefixEditor.show_for(self.controller, self)

    def _on_user_responses(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.user_response_editor import UserResponseEditor

        self._user_response_editor = UserResponseEditor.show_for(self.controller, self)

    def _on_game_saves(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.game_saves_manager import GameSavesManager

        self.nit_status.set_info(self.controller.current_game_summary())
        self._saves_manager = GameSavesManager.show_for(self.controller, self)

    def _on_mods_played(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.mod_play_viewer import ModPlayViewer

        self._mod_play_viewer = ModPlayViewer.show_for(self.controller, self)

    def _on_workshop(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.workshop_viewer import WorkshopViewer

        self._workshop_viewer = WorkshopViewer.show_for(self.controller, self)

    def _on_doc_organiser(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.doc_organiser import DocOrganiser

        # Scan the selected mods, or all mods when nothing is selected.
        names = self.selected_mod_names() or None
        self._doc_organiser = DocOrganiser.show_for(self.controller, names, self)

    def _on_wizard_builder(self) -> None:
        # VB enables this only when exactly one mod is selected.
        names = self.selected_mod_names()
        if self.controller is None or len(names) != 1:
            self.nit_status.set_info("Select a single mod first.")
            return
        from vaultkeeper.ui.dialogs.wizard_builder import WizardBuilder

        self._wizard_builder = WizardBuilder.show_for(self.controller, names[0], self)

    def _on_folder_mapping(self, start_tab: str = "Extensions") -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.folder_mapping import FolderMapping

        self._folder_mapping = FolderMapping.show_for(
            self.controller, start_tab, self
        )

    def _on_conflicts(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.conflicts_viewer import ConflictsViewer

        self._conflicts_viewer = ConflictsViewer.show_for(self.controller, self)

    def _on_dependencies(self) -> None:
        if self.controller is None:
            return
        names = self.selected_mod_names()
        if len(names) == 1:
            # Edit the selected mod's dependencies (VB DependencyManager for a mod).
            from vaultkeeper.ui.dialogs.dependency_editor import DependencyEditor

            self._dependency_editor = DependencyEditor.show_for(
                self.controller, names[0], self
            )
            self._dependency_editor.finished.connect(lambda _=0: self.refresh())
        else:
            # No single mod selected → show the whole-graph report.
            from vaultkeeper.ui.dialogs.dependency_manager import DependencyManager

            self._dependency_manager = DependencyManager.show_for(self.controller, self)

    def _on_analyse(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.installation_analyser import InstallationAnalyser

        self._analyser = InstallationAnalyser.show_for(self.controller, self)

    def _on_installation_manager(self) -> None:
        """Open the Installation Manager (named install sets — VB MsInstallationManager)."""
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.installation_manager import InstallationManager

        self._installation_manager = InstallationManager.show_for(self.controller, self)
        # Applying a set changes install state; refresh the main list when it closes.
        self._installation_manager.finished.connect(self.refresh)

    def _on_hak_patch_editor(self) -> None:
        """Open the Hak Patch editor (order patch-hak loading — VB MsHakPatchEditor)."""
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.hak_patch_editor import HakPatchEditor

        self._hak_patch_editor = HakPatchEditor.show_for(self.controller, self)

    def _on_create_original_restorers(self) -> None:
        """Back up pristine game originals into restorer mods (VB MsCreateOriginalRestorers)."""
        if self.controller is None:
            return
        self.nit_status.set_info("Creating original NWN installation restorers…")
        result = self.controller.create_original_restorers()
        self.refresh()
        self.nit_status.set_info(result["message"])

    def _on_alias_section(self) -> None:
        """Open the Alias Section editor (edit nwn.ini [Alias] — VB MsAliasSection).

        When the editor writes nwn.ini, re-open the profile so the new folder
        locations take effect (VB Restart after an alias change).
        """
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.alias_section_editor import AliasSectionEditor

        self._alias_editor = AliasSectionEditor.show_for(self.controller, self)

        def _after(_result=None):
            if getattr(self._alias_editor, "changed", False):
                self._reopen_with_new_paths()

        self._alias_editor.finished.connect(_after)

    def _on_mod_explorer(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.mod_explorer import ModExplorer

        self._mod_explorer = ModExplorer.show_for(self.controller, self)

    def _on_backup_data(self) -> None:
        if self.controller is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Backup Data", "vaultkeeper-backup.zip", "Zip archives (*.zip)"
        )
        if path:
            from pathlib import Path

            self.nit_status.set_info(self.controller.backup_data(Path(path)))

    def _on_restore_data(self) -> None:
        if self.controller is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore Data", "", "Zip archives (*.zip)"
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self,
            "Restore Data",
            "Restoring will overwrite the current profile data. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from pathlib import Path

        message = self.controller.restore_data(Path(path))
        self.refresh()
        self.nit_status.set_info(message)

    def _resolve_recovery_source(self, path: str):
        """Resolve a chosen ``*.json``/``*.zip`` path to a recovery source.

        A ``.json`` is used directly; a ``.zip`` (a Vaultkeeper backup) is searched
        for ``<current profile>.json`` and extracted to a temp dir — the port's
        equivalent of VB extracting the chosen Profile Data backup and reading
        ``<profile>\\ModData`` from it (NIT.Menu.vb:4938-4942 / 5099-5111). Returns
        ``None`` when nothing usable is found.
        """
        import tempfile
        from pathlib import Path

        from vaultkeeper.game.recovery import extract_profile_json_from_zip

        src = Path(path)
        if src.suffix.lower() == ".json":
            return src
        if src.suffix.lower() == ".zip":
            if self.controller is None or self.controller.store_path is None:
                return None
            profile_name = self.controller.store_path.stem
            dest_dir = Path(tempfile.mkdtemp(prefix="vaultkeeper-recover-"))
            return extract_profile_json_from_zip(src, profile_name, dest_dir)
        return None

    def _on_recover_groups(self) -> None:
        """Recover Group assignments from another profile (VB MsRecoverGroups)."""
        if self.controller is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Recover Groups", "", "Profile data (*.json *.zip)"
        )
        if not path:
            return
        source = self._resolve_recovery_source(path)
        if source is None:
            self.nit_status.set_info(
                "Unable to load recovery information from the selected file."
            )
            return
        changed = self.controller.recover_groups(source)
        self.refresh()
        self.nit_status.set_info(f"Mod Group changes: {changed:,}.")

    def _on_recover_properties(self) -> None:
        """Recover user mod-property data from another profile (VB MsRecoverModProperties)."""
        if self.controller is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Recover Mod Properties", "", "Profile data (*.json *.zip)"
        )
        if not path:
            return
        source = self._resolve_recovery_source(path)
        if source is None:
            self.nit_status.set_info(
                "Unable to load recovery information from the selected file."
            )
            return
        updated = self.controller.recover_mod_properties(source)
        self.refresh()
        self.nit_status.set_info(f"Mod property information recovered: {updated:,}.")

    def _on_download_project(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.download_project import DownloadProjectDialog

        selected = self.selected_mod_names()
        self._download_dialog = DownloadProjectDialog(
            self.controller, default_mod=selected[0] if selected else "", parent=self
        )
        # Refresh the mod list when the dialog closes (a download can create a mod).
        self._download_dialog.finished.connect(self.refresh)
        self._download_dialog.show()

    def _on_settings(self, start_tab: str = "") -> None:
        """Open Settings; Basic Settings starts on the Behaviour tab (VB BasicSettings)."""
        from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

        before = self._current_game_paths()
        settings = SettingsDialog.edit(
            parent=self, controller=self.controller, start_tab=start_tab
        )
        if settings is not None:
            # Reflect the recycle preference on the status bar toggle.
            self.nit_status.set_recycle(settings.recycle_on_delete)
            # Rebuild the Web + Run menus in case their entries were edited (VB
            # SetWebMenu / SetRunMenu).
            self.nit_menu.populate_web_menu(settings.web_links, self._open_url)
            self.nit_menu.populate_run_menu(settings.run_links, self._on_run_program)
            # Reflect the auto-delete-leto preference on the manual command's visibility.
            self._apply_leto_menu_visibility()
            # If the game paths changed, reopen the profile so they take effect now.
            if (settings.nwn_path, settings.game_user_path) != before:
                self._reopen_with_new_paths()
            self.nit_status.set_info("Settings saved.")

    def _current_game_paths(self) -> tuple:
        from vaultkeeper.config.settings import load_settings

        s = load_settings()
        return (s.nwn_path, s.game_user_path)

    def _reopen_with_new_paths(self) -> None:
        """Re-open the active profile with the freshly-edited game paths."""
        from vaultkeeper.ui.session import bootstrap_controller

        controller = bootstrap_controller()
        if controller is not None:
            self.set_controller(controller)
            self.nit_status.set_info("Game paths updated.")

    def _on_view_file(self, kind: str) -> None:
        if self.controller is None:
            return
        specs = {
            "MsLogFile": (self.controller.nit_log_path(), "Vaultkeeper Log File"),
            "MsNwnClientLogFile": (
                self.controller.game_file_path("logs", "nwclientlog1.txt"),
                "NWN Client Log File",
            ),
            "MsNwnEngineLogFile": (
                self.controller.game_file_path("logs", "nwenginelog.txt"),
                "NWN Engine Log File",
            ),
            "MsNWNIniFile": (
                self.controller.game_file_path("nwn.ini"), "NWN Ini File"
            ),
            "MsNwnSettingsFile": (
                self.controller.game_file_path("settings.tml"), "NWN Settings File"
            ),
            "MsNWNPlayerIniFile": (
                self.controller.game_file_path("nwnplayer.ini"), "NWN Player Ini File"
            ),
            "MsNwnPatchIniFile": (
                self.controller.game_file_path("nwnpatch.ini"), "NWN Patch Ini File"
            ),
            "MsNwnConfigIniFile": (
                self.controller.game_file_path("nwconfig.ini"), "NWN Config Ini File"
            ),
            "MsNwnToolsetIniFile": (
                self.controller.game_file_path("nwtoolset.ini"), "NWN Toolset Ini File"
            ),
        }
        path, title = specs.get(kind, (None, "File"))
        from vaultkeeper.ui.dialogs.text_viewer import TextViewer

        self._text_viewer = TextViewer.show_file(path, title, self)

    def _on_play(self, toolset: bool = False) -> None:
        """Launch NWN (or the toolset).

        When the game can be run as an awaitable process (a resolvable binary), it is
        launched non-detached and the finished signal drives play-session recording
        (VB exit processing). Otherwise (Steam URL / no binary) it is started detached
        with no exit detection.
        """
        if self.controller is None:
            return
        if getattr(self, "_game_process", None) is not None:
            self.nit_status.set_info("A game is already running.")
            return
        from datetime import datetime

        from PySide6.QtCore import QProcess

        what = "Toolset" if toolset else "Neverwinter Nights"

        # Awaitable launch: record the session on exit (only for the game, not toolset).
        if not toolset and self.controller.can_await_exit():
            argv = self.controller.launch_argv(wait=True)
            proc = QProcess(self)
            self._game_process = proc
            self._play_started = datetime.now()
            proc.finished.connect(lambda *_: self._on_game_exited())
            proc.start(argv[0], argv[1:])
            self.nit_status.set_info(f"Playing {what}…")
            return

        argv = self.controller.launch_argv(toolset=toolset)
        if not argv:
            self.nit_status.set_info("Neverwinter Nights install not found.")
            return
        if QProcess.startDetached(argv[0], argv[1:]):
            self.nit_status.set_info(f"Launched {what}.")
        else:
            self.nit_status.set_info(f"Could not launch {what}.")

    def _on_game_exited(self) -> None:
        """Process a finished play session (VB post-play exit processing)."""
        from datetime import datetime

        started = getattr(self, "_play_started", None)
        self._game_process = None
        if self.controller is None or started is None:
            return
        summary = self.controller.process_play_session(started, datetime.now())
        self.refresh()
        mods = summary.get("mods", {})
        if mods:
            names = ", ".join(sorted(mods))
            self.nit_status.set_info(f"Recorded play time for: {names}")
        else:
            self.nit_status.set_info("Finished playing (no play time recorded).")

    def _not_implemented(self) -> None:
        self.nit_status.set_info("That command is not available yet.")

    def _on_install(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            return
        message = self.controller.install(names)
        self.refresh()
        self.nit_status.set_info(message or "Install complete")

    def _on_uninstall(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            return
        message = self.controller.uninstall(names)
        self.refresh()
        self.nit_status.set_info(message or "Uninstall complete")

    def _on_rename(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or len(names) != 1:
            return
        old = names[0]
        new, ok = QInputDialog.getText(self, "Rename Mod", "New name:", text=old)
        new = new.strip()
        if not ok or not new or new == old:
            return
        if self.controller.rename_mod(old, new):
            self.refresh()
            self.nit_status.set_info(f"Renamed '{old}' to '{new}'")
        else:
            QMessageBox.warning(self, "Rename Mod", f"Could not rename to '{new}'.")

    def _on_properties(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or len(names) != 1:
            return
        props = self.controller.mod_properties(names[0])
        if props is None:
            return
        from vaultkeeper.ui.dialogs.mod_properties import ModPropertiesDialog

        dlg = ModPropertiesDialog(names[0], props, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.controller.set_mod_properties(names[0], **dlg.values())
        self.refresh()
        # Re-show the details for the (still-selected) mod.
        md = self.controller.pd.mod_item(names[0])
        if md is not None:
            self._show_details(md)
        self.nit_status.set_info(f"Updated properties for '{names[0]}'")

    def _on_edit_web_link(self) -> None:
        """Edit the selected mod's web page address (VB ``MsEditWebLink``)."""
        names = self.selected_mod_names()
        if self.controller is None or len(names) != 1:
            self.nit_status.set_info("Select a single mod first.")
            return
        mod = names[0]
        current = self.controller.mod_web_link(mod)
        prompt = f'Enter "{mod}" web page address (URL).'
        if current:
            prompt += "\nClear the field to remove the address."
        url, ok = QInputDialog.getText(self, "Mod's Web Page", prompt, text=current)
        if not ok:
            return
        result = self.controller.set_mod_web_link(mod, url)
        if result["ok"]:
            md = self.controller.pd.mod_item(mod)
            if md is not None:
                self._show_details(md)
        self.nit_status.set_info(result["message"])

    def _on_find(self) -> None:
        """Open the profile file-search dialog (VB ``MsFind`` on the mod list)."""
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.find_files import FindFilesDialog

        self._find_dialog = FindFilesDialog.show_for(
            self.controller, self._select_mod_by_name, self
        )

    def _select_mod_by_name(self, mod_name: str) -> None:
        """Select a mod in the list by name (VB ``SelectMod``)."""
        if self._tree.select_mod(mod_name):
            self._on_selection_changed()

    def _on_go_to_group(self) -> None:
        """Jump the mod list to a chosen group (VB ``MsGoToGroup``)."""
        from vaultkeeper.core import constants as C

        if self.controller is None:
            return
        groups = [
            g
            for g in self.controller.group_names()
            if not g.startswith(C.GROUP_HIDDEN_PREFIX)
        ]
        if not groups:
            self.nit_status.set_info("There are no groups to go to.")
            return
        name, ok = QInputDialog.getItem(
            self, "Go to Group", "Group:", groups, editable=False
        )
        if ok and name and self._tree.select_group(name):
            self._on_selection_changed()

    def _on_copy_name(self) -> None:
        """Copy the selected mod name(s) to the clipboard (VB ``MsCopyName``).

        VB copies from the active FileView; the mod list is the primary one, so we
        copy the selected mod names (one per line). The Contents pane has its own
        "Copy Name" in its right-click menu for file names.
        """
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText("\n".join(names))
        self.nit_status.set_info(f"Copied {len(names)} name(s).")

    def _on_copy_web_link(self) -> None:
        """Copy the selected mod's web link to the clipboard (VB ``MsCopyWebLink``)."""
        names = self.selected_mod_names()
        if self.controller is None or len(names) != 1:
            self.nit_status.set_info("Select a single mod first.")
            return
        link = self.controller.mod_web_link(names[0])
        if not link:
            self.nit_status.set_info(f"{names[0]} has no web link.")
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(link)
        self.nit_status.set_info(f"Copied {names[0]}'s web link.")

    def _confirm(self, title: str, text: str) -> bool:
        """Confirm a destructive action, honouring the confirm-actions preference
        (VB NitUserInterface.ConfirmActions). Returns True to proceed."""
        if self.controller is not None and not self.controller._settings().confirm_actions:
            return True
        return QMessageBox.question(self, title, text) == QMessageBox.StandardButton.Yes

    def _on_remove(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            return
        prompt = (
            f"Remove {len(names)} mod(s) from the profile?\n"
            "(The mod files on disk are not deleted.)"
        )
        if not self._confirm("Remove from Profile", prompt):
            return
        removed = self.controller.remove_mods(names)
        self.refresh()
        self.nit_status.set_info(f"Removed {removed} mod(s) from the profile")
