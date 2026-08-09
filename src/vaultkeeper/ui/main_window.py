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

from nwnfile.log import get_logger
from PySide6.QtCore import QSignalBlocker, Qt, QUrl
from PySide6.QtWidgets import (
    QCheckBox,
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
from vaultkeeper.ui.status_bar import (
    SELECT_HISTORY,
    SELECT_PLAY_TIME,
    SELECT_TEXT_FILE,
    NitStatusBar,
)

#: The status-bar icon state for each selection preference. Two vocabularies for
#: one idea, kept apart because one is a picture and the other is a setting.
_STATUS_SELECT_STATE = {
    "history": SELECT_HISTORY,
    "play_time": SELECT_PLAY_TIME,
    "text_file": SELECT_TEXT_FILE,
}

log = get_logger(__name__)


def _shortened_link(url: str) -> str:
    """A URL short enough to sit on a summary line without pushing it out of view."""
    trimmed = url.split("://", 1)[-1].rstrip("/")
    return trimmed if len(trimmed) <= 60 else trimmed[:57] + "…"


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
        # Double-click a mod to install it, or uninstall it if it is installed
        # (VB FvMods_MouseDoubleClick). Groups keep Qt's expand/collapse, which
        # is what VB's DoubleClickAction guard leaves them.
        self._tree.itemDoubleClicked.connect(self._on_mod_double_clicked)
        self._tree.mods_dropped_on_group.connect(self._on_mods_dropped_on_group)
        # Return renames on macOS, Finder-style (see FileView.keyPressEvent).
        self._tree.rename_requested.connect(self._on_rename)
        # Clicking a mod's status icon installs or uninstalls it (newtopic28).
        self._tree.state_icon_clicked.connect(self._on_state_icon_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_mods_context_menu)
        # "You can click the Profile name to refresh the Mod List" — the heading
        # is where VB shows which profile is loaded, and the port showed it
        # nowhere at all.
        self._tree.header().setSectionsClickable(True)
        self._tree.header().sectionClicked.connect(lambda _i: self.refresh())

        self._contents = ContentsView()
        # Contents-pane file actions (VB CmContents): double-click views a file,
        # right-click offers View / Delete.
        self._contents_mod: str | None = None
        # Cut/Copy/Paste clipboard for Contents files: (mod, folder, filename, is_cut).
        self._file_clipboard: tuple | None = None
        self._contents.itemDoubleClicked.connect(self._on_view_contents_file)
        # Remember what was picked, so "whatever was selected last time" means
        # something the next time this mod is opened.
        self._contents.itemSelectionChanged.connect(self._remember_contents_selection)
        self._contents.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._contents.customContextMenuRequested.connect(
            self._show_contents_context_menu
        )
        self._mod_info = QLabel("")
        self._mod_info.setWordWrap(True)
        self._mod_info.setTextFormat(Qt.TextFormat.RichText)
        self._mod_info.linkActivated.connect(self._on_mod_info_link)
        self._mod_info.setMargin(6)
        self._mod_info.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._details_list = QTreeWidget()
        self._details_list.setHeaderLabels(["Property", "Value"])
        self._details_list.setRootIsDecorated(False)
        # "You can click the heading to toggle the Automatic Properties Panel
        # Height option" — the same switch as the Options menu item.
        self._details_list.header().setSectionsClickable(True)
        self._details_list.header().sectionClicked.connect(
            lambda _i: self._on_toggle_properties_height()
        )
        # The properties list is read-only; the lower pane is the editable Mod Notes.
        self._details = QTextEdit()
        self._details.setPlaceholderText("Mod notes…")
        self._notes_mod: str | None = None  # the mod whose notes are loaded
        from vaultkeeper.config.settings import load_settings as _load

        #: Where each mod's notes were last left, restored on reselection.
        self._notes_positions: dict[str, int] = dict(_load().notes_positions)

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
        # Held so Reset Window Layout can put them back (VB MsResetWindow).
        self._splitters = (splitter, sc_mod, sc_contents, sc_details)
        #: The properties list sits above the notes; Automatic Properties Panel
        #: Height moves this one.
        self._properties_splitter = sc_details

        # Command chrome (faithful ports of the VB ribbon/toolbar/status bar).
        self.ribbon = Ribbon()
        self.ribbon.action_triggered.connect(self._on_command)
        self.ribbon.action_right_clicked.connect(self._on_command_right_clicked)
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
        # Both of these were emitting into the void (newtopic34).
        self.nit_status.mod_count_clicked.connect(self._on_mod_count_clicked)
        self.nit_status.select_file_clicked.connect(self._on_selection_preferences)
        # The rest of the status bar's icons emitted signals nobody listened to,
        # so every one of them was dead to the click (VB's Status Bar topic
        # describes them all as clickable, with a second screen on the right
        # button — VB Bt*_MouseUp).
        self.nit_status.group_clicked.connect(self._on_go_to_group)
        self.nit_status.info_clicked.connect(lambda: self.nit_status.set_info(""))
        self.nit_status.wizard_clicked.connect(self._on_wizard_builder)
        self.nit_status.wizard_right_clicked.connect(self._on_wizard_builder)
        self.nit_status.character_clicked.connect(self._on_characters)
        self.nit_status.character_right_clicked.connect(self._on_characters)
        self.nit_status.select_file_right_clicked.connect(self._on_doc_organiser)
        self.nit_status.recycle_right_clicked.connect(self._on_open_recycle_bin)
        self.nit_status.health_clicked.connect(
            lambda: self._on_view_file("MsNwnClientLogFile")
        )
        # "Display details about files added, removed or changed in the NWN
        # installation folder" — its own tooltip, promising something no click
        # delivered. That report is the conflicts viewer.
        self.nit_status.file_check_clicked.connect(self._on_conflicts)
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
            "<p>Use <b>File &rarr; Load Profile</b> (or <b>Open</b>) to create one. "
            "You will be asked for your Neverwinter Nights <b>installation</b> — the "
            "folder holding <tt>nwmain</tt>.</p>"
            # Enhanced Edition has two folders people call "my Neverwinter Nights
            # folder", and mods live in the other one. Saying so here saves the
            # first wrong guess, and says where to correct it.
            "<p>On Enhanced Edition your mods and saves live somewhere else again — "
            "in <b>Documents &rarr; Neverwinter Nights</b>. Vaultkeeper looks for that "
            "by itself; if it guesses wrong, set it under "
            "<b>Options &rarr; Settings &rarr; Locations</b>.</p>" + self._import_hint()
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
        # Give the window the shortcut-bearing actions directly. A QAction in a
        # menu bar resolves its shortcut through the menu bar's window, which is
        # this one — but only once the platform has made the window active, and
        # relying on that made Ctrl+G do nothing on a window that had not been
        # clicked yet. Adding them here puts them in scope from the start.
        for act in self.nit_menu.shortcut_actions():
            self.addAction(act)
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

        # The toolbar as the user left it: its contents and whether the captions
        # show (VB's Toolbar Editor + MsShowText).
        from vaultkeeper.config.settings import load_settings as _load_toolbar
        from vaultkeeper.ui.quick_toolbar import items_from_settings

        _toolbar_settings = _load_toolbar()
        if _toolbar_settings.quick_toolbar_items:
            self.quick_toolbar.populate(
                items_from_settings(_toolbar_settings.quick_toolbar_items)
            )
        self.quick_toolbar.set_show_text(_toolbar_settings.toolbar_show_text)
        _show_text = self.nit_menu.action("MsShowText")
        if _show_text is not None:
            # Signals blocked: ticking it *is* the command, so setting the
            # initial state would otherwise save the settings on every launch.
            _show_text.blockSignals(True)
            _show_text.setChecked(_toolbar_settings.toolbar_show_text)
            _show_text.blockSignals(False)

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
        # Ctrl+click opens straight onto the per-day report (VB reads
        # CtrlKeyDown and passes it to PlayDataManager.View as showReport).
        from PySide6.QtWidgets import QApplication

        wants_report = bool(
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier
        )
        if not wants_report and self.controller.pending_play_report()["count"] > 0:
            from vaultkeeper.ui.dialogs.play_data_view_pending import (
                PlayDataViewPending,
            )

            self._play_data_pending = PlayDataViewPending.show_for(self.controller, self)
            return
        from vaultkeeper.ui.dialogs.play_data_viewer import PlayDataViewer

        self._play_data_viewer = PlayDataViewer.show_for(
            self.controller, self, show_report=wants_report
        )

    def _update_played_info(self, mod_name: str | None = None) -> None:
        """Refresh the right-aligned play-time readout (VB ``Defs.TitleInfo``).

        It reports the *game*, not the selection — the mod name is accepted and
        ignored so the existing selection hooks keep it current. It used to show
        the selected mod's time and nothing otherwise, which meant most people
        never saw it at all.
        """
        if self.controller is None:
            self._played_info.setText("")
            self._played_info.setToolTip("")
            return
        info = self.controller.play_time_info()
        self._played_info.setText(info["text"])
        self._played_info.setToolTip(info["tooltip"])

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

    def _save_notes_positions(self) -> None:
        """Write the remembered notes positions out (called on the way out)."""
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings()
        if not settings.remember_text_positions:
            return
        self._remember_notes_position()
        if settings.notes_positions != self._notes_positions:
            settings.notes_positions = dict(self._notes_positions)
            save_settings(settings)

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
        elif item_id == "MsShowText":
            from vaultkeeper.config.settings import load_settings, save_settings

            settings = load_settings()
            settings.toolbar_show_text = checked
            save_settings(settings)
            self.quick_toolbar.set_show_text(checked)
        elif item_id == "MsOriginalPortraits":
            self._on_original_portraits(checked)
        elif item_id == "MsPropertiesHeight":
            from vaultkeeper.config.settings import load_settings, save_settings

            settings = load_settings()
            if settings.auto_properties_height != checked:
                settings.auto_properties_height = checked
                save_settings(settings)
            self._apply_properties_height()

    # -- Recent Mods (VB MsRecentMods) ------------------------------------- #
    def _record_recent_mod(self, name: str) -> None:
        """Push a selected mod to the front of the Recent Mods list (VB Manager.Add)."""
        from vaultkeeper.config.settings import load_settings

        if not name:
            return
        settings = load_settings()
        recent = [n for n in self._recent_mods if n != name]
        recent.insert(0, name)
        max_recent = max(1, settings.max_recent_mods)
        # Trimming drops the oldest — except a pinned one, which is exactly the
        # mod the user asked not to lose.
        pinned = set(settings.pinned_recent_mods)
        kept = recent[:max_recent]
        kept += [n for n in recent[max_recent:] if n in pinned]
        self._recent_mods = kept
        self._rebuild_recent_mods_menu()

    def _rebuild_recent_mods_menu(self) -> None:
        """Re-render the Recent Mods submenu from the tracked list."""
        from vaultkeeper.config.settings import load_settings

        # Drop names no longer in the profile (VB Manager.Remove on delete/rename).
        if self.controller is not None:
            self._recent_mods = [
                n for n in self._recent_mods if self.controller.pd.mod_item(n) is not None
            ]
        settings = load_settings()
        # Pinned first, then the rest in order of use: a pinned mod is one you
        # keep coming back to, and burying it under this morning's browsing is
        # the thing pinning exists to stop.
        pinned = [n for n in settings.pinned_recent_mods if n in self._recent_mods]
        rest = [n for n in self._recent_mods if n not in pinned]
        self.nit_menu.populate_recent_mods(
            pinned + rest,
            self._select_mod_by_name,
            numbered=settings.number_recent_mods,
            pinned=pinned,
            on_action=self._on_recent_mod_action,
        )

    def _on_recent_mod_action(self, what: str, name: str) -> None:
        """Pin / Unpin / Remove from the Recent Mods list (VB's Actions menu)."""
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings()
        pinned = [n for n in settings.pinned_recent_mods if n != name]
        if what == "pin":
            pinned.append(name)
        elif what == "remove":
            self._recent_mods = [n for n in self._recent_mods if n != name]
        settings.pinned_recent_mods = pinned
        save_settings(settings)
        self._rebuild_recent_mods_menu()
        self.nit_status.set_info(
            {
                "pin": f"'{name}' will stay in Recent Mods.",
                "unpin": f"'{name}' is no longer pinned.",
                "remove": f"'{name}' removed from Recent Mods.",
            }.get(what, "")
        )

    def set_controller(self, controller: ProfileController) -> None:
        """Swap in a new active profile controller and repopulate."""
        self.controller = controller
        self._install_prompter()
        self.refresh()
        self._detect_workshop_changes()
        self._notify_config_drift()

    def _detect_workshop_changes(self) -> None:
        """Notice new or changed Steam subscriptions on load (VB ``newtopic20``).

        "The Installer Tool detects new and changed Workshop Subscriptions when
        you […] Start the Installer Tool […] Load or reload an Enhanced Edition
        Profile." Only the Tools menu and the viewer did it here, so something
        subscribed to yesterday stayed invisible until someone went looking for
        it.

        Best-effort and quiet: a non-Steam install says so and is ignored, and
        nothing here may keep a profile from opening.
        """
        if self.controller is None or not self.controller.ctx.is_ee:
            return
        try:
            diff = self.controller.workshop_refresh()
        except Exception:
            return
        if diff["added"] or diff["updated"] or diff["unsubscribed"]:
            self.nit_status.set_info(diff["summary"])

    def _notify_config_drift(self) -> None:
        """Non-modal notice if the game's config changed since we last saw it."""
        if self.controller is None:
            return
        # Start-up housekeeping while we are here (VB NitStartUp): today counts
        # towards the play-time average whether or not it is played.
        self.controller.note_play_day()
        # The check ran unconditionally, so "Check the game configuration for
        # changes on startup" could be unticked and changed nothing.
        if not self.controller._settings().validate_game_config_on_startup:
            return
        changes = self.controller.startup_config_check()
        if changes:
            names = ", ".join(sorted({c.path.name for c in changes}))
            self.nit_status.set_info(f"Note: game config changed ({names})")

    def _on_setup(self) -> None:
        """First-run flow: locate the NWN folder, name a profile, open it."""
        # "installation ... where nwmain.exe is", not "your Neverwinter Nights
        # folder": on EE there are two of those, and the other one — the user
        # folder under Documents, where mods and saves actually live — is found
        # automatically. Asked plainly, people pick the wrong one.
        nwn_dir = QFileDialog.getExistingDirectory(
            self,
            "Locate your Neverwinter Nights installation (the folder holding nwmain)",
        )
        if not nwn_dir:
            return
        name, ok = QInputDialog.getText(self, "Profile", "Profile name:", text="My Mods")
        if not ok or not name.strip():
            return

        # The one thing that cannot be changed afterwards, so it is asked now
        # (definenewprofiles.htm). Pre-answered from what is actually installed:
        # the two editions keep their mods in different places, and a profile
        # opened as the wrong one has every file key wrong.
        from nwnfile.editions import Edition
        from nwnfile.locations import discover_installs

        detected = next(
            (i for i in discover_installs() if str(i.root) == nwn_dir), None
        )
        default_ee = detected is None or detected.edition == Edition.ENHANCED
        editions = ["Enhanced Edition", "Neverwinter Nights (1.69)"]
        choice, ok = QInputDialog.getItem(
            self,
            "Profile",
            "Which Neverwinter Nights is this profile for?\n"
            "This cannot be changed later.",
            editions,
            0 if default_ee else 1,
            False,
        )
        if not ok:
            return

        from vaultkeeper.ui.session import configure_profile

        try:
            controller = configure_profile(
                nwn_dir, name.strip(), is_ee=choice == editions[0]
            )
        except OSError as exc:
            QMessageBox.warning(self, "Set Up Profile", f"Could not create the profile:\n{exc}")
            return
        self.set_controller(controller)
        self.nit_status.set_info(f"Profile '{name.strip()}' ready")

    # -- Profile switching ------------------------------------------------- #
    def _on_mod_count_clicked(self) -> None:
        """The installed/total count opens the Mod Explorer (VB ``BtModCount``).

        The number is a summary of the whole list; the Explorer is where that
        list can be sorted and filtered, so that is what the summary leads to.
        """
        self._on_mod_explorer()

    def _on_selection_preferences(self) -> None:
        """Choose which file a mod's Contents pane opens on (VB Selection Prefs)."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu

        from vaultkeeper.config.settings import load_settings, save_settings
        from vaultkeeper.ui import selection_prefs

        settings = load_settings()
        menu = QMenu(self)
        menu.addAction("When a mod is selected, open its Contents on:").setEnabled(False)
        menu.addSeparator()
        actions = {}
        for value in selection_prefs.PREFERENCES:
            act = menu.addAction(selection_prefs.LABELS[value])
            act.setCheckable(True)
            act.setChecked(settings.selection_preference == value)
            actions[act] = value
        chosen = menu.exec(QCursor.pos())
        if chosen is None or chosen not in actions:
            return
        settings.selection_preference = actions[chosen]
        save_settings(settings)
        self.nit_status.set_select_state(_STATUS_SELECT_STATE[actions[chosen]])
        if self._contents_mod is not None:
            self._apply_selection_preference(self._contents_mod)
        self.nit_status.set_info(
            f"Contents opens on: {selection_prefs.LABELS[actions[chosen]].lower()}."
        )

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

    def offer_player_excludes(self) -> None:
        """Ask once whether this is a player's or a builder's collection.

        VB's ``CheckPlayerExcludes``. It decides what Create Installer leaves
        out — builder resources, script templates, and the starter modules that
        ship inside community packs — and it is the last thing anybody wants to
        discover after building thirty installers.
        """
        if self.controller is None or not self.controller.player_excludes_pending():
            return
        box = QMessageBox(self)
        box.setWindowTitle("Player or Mod Builder?")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            "Do you play modules, or build them?\n\n"
            "A player's installers can leave out the parts only a builder needs: "
            "builder resources, script templates, and the starter modules that "
            "come inside community packs like CEP.\n\n"
            "Either way, Settings → Map Excludes is where this is changed later."
        )
        player = box.addButton("I play modules", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("I build modules", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        result = self.controller.answer_player_excludes(
            player=box.clickedButton() is player
        )
        self.nit_status.set_info(result["message"])

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
        self._show_profile_name()
        self._populate_mod_selector()
        self._update_status()
        self._update_title()
        # The play-time readout reports the game, so it is current from the
        # moment a profile opens rather than waiting for a mod to be clicked.
        self._update_played_info()
        total, _ = self.controller.counts()
        if total == 0:
            self._details.setHtml(
                "<h3>This profile has no mods yet</h3>"
                "<p>Add mods with <b>Mods &rarr; New Mod</b>, or import an existing "
                "collection.</p>" + self._import_hint()
            )

    def _show_profile_name(self) -> None:
        """Name the loaded profile on the mod list's heading (VB Profile Name)."""
        name = ""
        if self.controller is not None and self.controller.store_path is not None:
            name = self.controller.store_path.stem
        self._tree.headerItem().setText(0, name or "Mods")
        self._tree.header().setToolTip(
            f"Profile: {name}\nClick to refresh the mod list" if name else ""
        )

    def _on_original_portraits(self, wanted: bool) -> None:
        """Fetch (or drop) BioWare's own portraits (VB ``MsOriginalPortraits``).

        The game keeps its built-in portraits inside its data files, where
        nothing here can read them, so a character rolled with one shows no
        picture at all. The Vault publishes them as a reference archive; this
        fetches it on request, because it is a ~150 MB download that unpacks to
        roughly 350 MB and nobody should meet that by accident.
        """
        from PySide6.QtWidgets import QApplication

        if self.controller is None:
            return
        action = self.nit_menu.action("MsOriginalPortraits")

        def set_tick(state: bool) -> None:
            if action is not None:
                action.blockSignals(True)
                action.setChecked(state)
                action.blockSignals(False)

        if not wanted:
            result = self.controller.remove_original_portraits()
            self.nit_status.set_info(result["message"])
            return

        if self.controller.has_original_portraits():
            self.nit_status.set_info("BioWare's portraits are already here.")
            return

        if (
            QMessageBox.question(
                self,
                "Show BioWare's Portrait Images",
                "Download BioWare's portrait files?\n\n"
                "Character summaries and the Portrait Manager will then show the "
                "game's built-in portraits, which live inside the game's own data "
                "files where this cannot read them.\n\n"
                "The download is around 150 MB and uses about 350 MB once "
                "unpacked.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            set_tick(False)
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.controller.download_original_portraits(
                on_phase=lambda text: (
                    self.nit_status.set_info(text),
                    QApplication.processEvents(),
                )
            )
        finally:
            QApplication.restoreOverrideCursor()

        set_tick(bool(result["ok"]))
        self.nit_status.set_info(result["message"])
        if not result["ok"]:
            QMessageBox.warning(
                self, "Show BioWare's Portrait Images", result["message"]
            )

    def _on_toggle_properties_height(self) -> None:
        """Flip Automatic Properties Panel Height (VB ``MsPropertiesHeight``).

        Driven from two places — this menu item and the Properties heading —
        so both go through here and both leave the menu tick correct.
        """
        from vaultkeeper.config.settings import load_settings, save_settings

        wanted = not load_settings().auto_properties_height
        action = self.nit_menu.action("MsPropertiesHeight")
        if action is not None:
            # Setting the tick emits toggled, which does the saving and the
            # resizing — one path, and the menu can never disagree with the
            # setting.
            action.setChecked(wanted)
        else:  # pragma: no cover - the item is always in the menu
            settings = load_settings()
            settings.auto_properties_height = wanted
            save_settings(settings)
        self.nit_status.set_info(
            "Automatic Properties Panel Height is " + ("on." if wanted else "off.")
        )

    def _apply_properties_height(self) -> None:
        """Size the properties pane to what it is showing, when that is enabled.

        Off, the splitter is left exactly where the user put it — an automatic
        height that fights a drag is worse than no automatic height.
        """
        from vaultkeeper.config.settings import load_settings

        if not load_settings().auto_properties_height:
            return
        splitter = self._properties_splitter
        if splitter is None:
            return
        rows = self._details_list.topLevelItemCount()
        # VB: the file-list height matches the Mod Properties panel, and a
        # file's own details are the five lines it has.
        wanted = max(1, rows) * max(1, self._details_list.sizeHintForRow(0)) + 32
        total = sum(splitter.sizes())
        if total <= 0:
            return
        top = max(60, min(wanted, int(total * 0.6)))
        splitter.setSizes([top, max(1, total - top)])

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
        group = self._tree.group_header_at(pos)
        if group is not None:
            self._show_group_context_menu(group, pos)
            return
        menu = self._build_mods_context_menu()
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _show_group_context_menu(self, group: str, pos) -> None:
        """Right-click a group header → Rename / Delete Group (VB group actions)."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction("Rename Group…", lambda: self._on_rename_group(group))
        menu.addAction("Delete Group…", lambda: self._on_delete_groups([group]))
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _on_rename_group(self, group: str) -> None:
        """Rename a group (VB rename-group). Reserved groups are not renamable."""
        if self.controller is None:
            return
        new, ok = QInputDialog.getText(
            self, "Rename Group", "New group name:", text=group
        )
        new = new.strip()
        if not ok or not new or new == group:
            return
        if self.controller.rename_group(group, new):
            self.refresh()
            self.nit_status.set_info(f"Renamed group '{group}' to '{new}'.")
        else:
            self.nit_status.set_info(f"Could not rename group '{group}'.")

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
        """Persist unsaved notes, where they were left, and the geometry."""
        self._save_current_notes()
        self._save_notes_positions()
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
        self._apply_selection_preference(md.mod_name)

    def _apply_selection_preference(self, mod_name: str) -> None:
        """Open the Contents pane on whatever the Selection Preferences icon says."""
        from vaultkeeper.config.settings import load_settings
        from vaultkeeper.ui import selection_prefs

        settings = load_settings()
        remembered = settings.contents_selection.get(mod_name)
        chosen = selection_prefs.choose(
            settings.selection_preference,
            self._contents.files(),
            remembered=tuple(remembered.split("/", 1)) if remembered else None,
        )
        if chosen is not None:
            self._contents.select_file(chosen)

    def _remember_contents_selection(self) -> None:
        """Note what is selected, so "last time" means something next time."""
        from vaultkeeper.config.settings import load_settings, save_settings

        selected = self._contents.selected_file()
        if self._contents_mod is None or selected is None:
            return
        settings = load_settings()
        key = f"{selected[0]}/{selected[1]}"
        if settings.contents_selection.get(self._contents_mod) == key:
            return
        settings.contents_selection[self._contents_mod] = key
        save_settings(settings)

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
        from nwnfile.character import CharacterFile
        from nwnfile.formats.bic_reader import BicFileReader

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
            item = QTreeWidgetItem([prop, value])
            if prop == "State":
                # statusicons.htm: "Descriptions of the status icons are
                # displayed in the Mod Properties and Details Property panels."
                # A title-cased enum name is a label, not an explanation.
                item.setToolTip(1, md.mod_state.describe())
            self._details_list.addTopLevelItem(item)
        self._details_list.resizeColumnToContents(0)

        # Mod info (VB TlModInfoContainer): a short summary line.
        state = md.mod_state.name.replace("_", " ").title()
        self._mod_info.setToolTip(md.mod_state.describe())
        play = ""
        if self.controller is not None:
            loop = self.controller.play_loop
            if loop is not None:
                played = loop.play_time(md.mod_name)
                if played.total_seconds() > 0:
                    play = f" · played {loop.play_data.format_time(played, '')}"
        # The web link as an actual link, and an invitation when there is none
        # (VB's Add Link icon, which becomes the Download Page icon once set —
        # recordamodswebpagelink.htm). It was printed as plain text here, so the
        # one thing anybody wants to do with a URL could not be done with it.
        from html import escape

        if md.web_link:
            link = (
                f'  ·  <a href="{escape(md.web_link, quote=True)}">'
                f"{escape(_shortened_link(md.web_link))}</a>"
            )
        else:
            link = '  ·  <a href="vaultkeeper:add-link">Add link…</a>'
        self._mod_info.setText(
            f"{escape(md.mod_name)} — {escape(state)}{escape(play)}{link}"
        )
        self._mod_info.setToolTip(md.web_link or "Record this mod's download page")

        # Editable Mod Notes (VB per-mod .rtf). Persist the previously-shown mod first.
        self._remember_notes_position()
        self._save_current_notes()
        self._notes_mod = md.mod_name
        if self.controller is not None:
            self._details.setPlainText(self.controller.read_notes(md.mod_name))
        self._details.document().setModified(False)
        self._restore_notes_position(md.mod_name)

    def _remember_notes_position(self) -> None:
        """Note where the notes were left (VB ``ScrollPositions.RtModNotes``).

        Kept in memory and written with the rest of the settings: a mod's notes
        can be pages long, and coming back to the top of them every time is the
        sort of small thing that makes a tool tiring.
        """
        from vaultkeeper.config.settings import load_settings

        if self._notes_mod is None or not load_settings().remember_text_positions:
            return
        self._notes_positions[self._notes_mod] = self._details.textCursor().position()

    def _restore_notes_position(self, mod_name: str) -> None:
        from vaultkeeper.config.settings import load_settings

        if not load_settings().remember_text_positions:
            return
        position = self._notes_positions.get(mod_name)
        if not position:
            return
        cursor = self._details.textCursor()
        cursor.setPosition(min(position, len(self._details.toPlainText())))
        self._details.setTextCursor(cursor)
        self._details.ensureCursorVisible()

    def _on_clear_text_positions(self) -> None:
        """Forget every remembered notes position (VB ``MsClearScrollInfo``).

        The confirmation doubles as the way to turn the remembering off, which
        is what VB's does — someone clearing these is often someone who did not
        want them kept.
        """
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings()
        box = QMessageBox(self)
        box.setWindowTitle("Clear Text Position Information")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            f"Forget where the notes were left for {len(settings.notes_positions):,} "
            "mod(s)?"
        )
        keep = QCheckBox("Go on remembering text positions")
        keep.setChecked(settings.remember_text_positions)
        box.setCheckBox(keep)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        settings.notes_positions = {}
        settings.remember_text_positions = keep.isChecked()
        save_settings(settings)
        self._notes_positions = {}
        self.nit_status.set_info("Text position information cleared.")

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
            # Also a checkable toggle, and also driven from a second place (the
            # Properties panel heading) — see _on_toggle_properties_height.
            "MsPropertiesHeight",
            # A checkable toggle too: ticking it downloads BioWare's portraits.
            "MsOriginalPortraits",
            # Icons with or without their captions.
            "MsShowText",
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
            "MsFindWebLink": self._on_find_web_link,
            "MsCheckForUpdates": self._on_check_for_mod_updates,
            # Copy the selected mod name(s) to the clipboard.
            "MsCopyName": self._on_copy_name,
            "TsCopyName": self._on_copy_name,
            # Find files across the profile.
            "MsFind": self._on_find,
            "TsFind": self._on_find,
            # Bulk find-and-rename across mod names (VB MsFindAndRename).
            "MsFindAndRename": self._on_find_and_rename,
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
            "MsValidateModWebLinks": self._on_validate_mod_web_links,
            # Options-menu housekeeping — all three were greyed out as "not yet
            # available" while doing nothing more than resetting local state.
            "MsResetWindow": self._on_reset_window_layout,
            "MsDisplaySettings": lambda: self._on_view_file("MsDisplaySettings"),
            "RbnDisplaySettings": lambda: self._on_view_file("MsDisplaySettings"),
            "MsOpenRulesFile": lambda: self._on_view_file("MsOpenRulesFile"),
            "MsViewClipboard": self._on_view_clipboard,
            # Move the selected Contents file elsewhere (VB MsMoveToFolder /
            # MsMoveToHistory), the two halves of the documented mod-update
            # workflow: put the new file in, keep the old one.
            "MsMoveToFolder": self._on_move_to_folder,
            "MsMoveToHistory": self._on_move_to_history,
            "MsClearWaitCursors": self._on_clear_wait_cursors,
            "MsClearSelectionHistory": self._on_clear_selection_history,
            "MsValidateInstalledData": lambda: self._maintenance("validate_installed_data"),
            "MsValidateMovieFiles": self._on_validate_movie_files,
            "MsValidate": self._on_validate_neverwinter_nights,
            "MsRefreshWorkshopFiles": self._on_refresh_workshop_files,
            "MsUpdateEeFiles": self._on_update_ee_files,
            "MsCustomise": self._on_customise_toolbar,
            "MsUpdateNow": self._on_check_for_update,
            "MsResetWebMenu": self._on_check_web_menu_links,
            # New folder / text file / rich text file, in the selected mod.
            "MsClearScrollInfo": self._on_clear_text_positions,
            "MsNewFolder": self._on_new_contents_folder,
            "MsNewTextFile": lambda: self._on_new_contents_file(".txt", "Text"),
            "MsNewRtfFile": lambda: self._on_new_contents_file(".rtf", "Rich Text"),
            "MsSendDiagInfo": self._on_send_diagnostics,
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
            "MsSaveGameEditor": self._on_save_game_editor,
            "MsPlayNeverwinterNights": self._on_play,
            "TsPlayNeverwinterNights": self._on_play,
            "RbnPlay": self._on_play,
            "MsToolset": lambda: self._on_play(toolset=True),
            "RbnToolset": lambda: self._on_play(toolset=True),
            "MsModsPlayed": self._on_mods_played,
            "MsWorkshopViewer": self._on_workshop,
            # The ribbon's own id. Without it the button greys itself out as
            # "not yet available" while the very same screen sits on the Tools
            # menu, working — which reads as a broken feature, not a missing one.
            "RbnManageWorkshop": self._on_workshop,
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
            "MsBackupManager": self._on_backup_manager,
            "MsBackupData": self._on_backup_data,
            "RbnBackupData": self._on_backup_data,
            "MsRestoreData": self._on_restore_data,
            # VB has only the ribbon button; there is no menu id for either.
            "RbnExportSettings": self._on_export_settings,
            "MsExportMods": self._on_export_mods,
            "MsImportMods": self._on_import_mods,
            "RbnRestoreData": self._on_restore_data,
            # Downloads (Vault).
            "MsDownloadProject": self._on_download_project,
            "RbnDownloadProject": self._on_download_project,
            "TsDownloadProject": self._on_download_project,
            # Downloads (the PRC-ified Drive collection) — added by this port.
            "RbnPrcModule": self._on_prc_module,
            # Settings. VB has two distinct surfaces: BasicSettings (a small curated
            # Behaviour/User-Interface dialog whose Advanced button chains into the
            # full Settings) and the full per-preference Settings browser.
            "MsSettings": self._on_settings,
            "MsBasicSettings": self._on_basic_settings,
            "RbnAdvancedSettings": self._on_settings,
            "RbnBasicSettings": self._on_basic_settings,
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
        """Open a new issue on the project, pre-filled (VB ``MsSendFeedback``).

        VB drafts an email to its author's personal support address. This used to
        copy that address verbatim, which sent Vaultkeeper's bug reports to
        Surazal — who maintains the original, not this port, and did not sign up
        to answer for it. Feedback belongs where the code is.

        The environment block is filled in here because it is the part everyone
        forgets and everyone gets asked for. Nothing is sent: the browser opens
        on a pre-filled form the user can read, edit and abandon.
        """
        from PySide6.QtGui import QDesktopServices

        from vaultkeeper.ui.feedback import feedback_url

        QDesktopServices.openUrl(QUrl(feedback_url()))

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
        """Create a mod, asking for its group as well as its name (VB New Mod).

        ``addanewmod.htm``: "If the Group shown is not the one you want to use
        for the new Mod, select the correct Group from the dropdown list." Only
        the name was asked for here, so every new mod landed in the default
        group and had to be dragged out of it.
        """
        if self.controller is None:
            return
        name, ok = QInputDialog.getText(self, "New Mod", "Mod name:")
        if not ok or not name.strip():
            return

        group = self._ask_group_for_new_mod()
        if group is None:
            return
        if self.controller.create_mod(name.strip(), group):
            self.refresh()
            self._select_mod_by_name(name.strip())  # "Your new Mod is selected"
            self.nit_status.set_info(f"Created mod '{name.strip()}'")
        else:
            self.nit_status.set_info(f"Mod '{name.strip()}' already exists")

    def _ask_group_for_new_mod(self) -> str | None:
        """The group for a new mod, defaulted to the one in view. None = cancelled.

        No question at all when the profile has no groups yet: a dropdown with
        one entry is a dialog that teaches people to click through dialogs.
        """
        from vaultkeeper.core import constants as C

        groups = [
            g
            for g in self.controller.group_names()
            if not g.startswith(C.GROUP_HIDDEN_PREFIX)
        ]
        if not groups:
            return ""
        selected = self.selected_mod_names()
        current = ""
        if selected:
            md = self.controller.pd.mod_item(selected[0])
            current = self.controller.group_label(md.group) if md is not None else ""
        options = ["No Group", *groups]
        index = options.index(current) if current in options else 0
        choice, ok = QInputDialog.getItem(
            self, "New Mod", "Group:", options, index, False
        )
        if not ok:
            return None
        return "" if choice == "No Group" else choice

    def _on_create_installer(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            self.nit_status.set_info("Select a mod first.")
            return
        copied = 0
        built = 0
        last_message = ""
        settings = self.controller._settings()
        for name in names:
            # Whether it was installed *before* the rebuild: afterwards the game
            # is holding the old payload, which is what installer_restore exists
            # to put right (VB BehaviourInstallerRestore).
            was_installed = self.controller._mod_installed(name)
            # RunWizard: present the installer wizard's choices before building.
            choice, checked = self._run_installer_wizard(name)
            result = self.controller.build_installer_payload(
                name, wizard_choice=choice, wizard_checked=checked
            )
            if result["ok"]:
                built += 1
                copied += result["copied"]
                # Install-after-create preference (VB BehaviourInstallerInstall).
                if self._install_after_create():
                    if not was_installed:
                        self.controller.install([name])
                elif settings.installer_restore and was_installed:
                    # Only put back what was already installed, so the game stops
                    # running the payload that was just replaced.
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

    def _on_validate_neverwinter_nights(self) -> None:
        """Report files that do not belong in the game's folders (VB ``MsValidate``).

        A list with tick boxes rather than VB's delete-the-lot button: run
        against a real installation every finding was legitimate (PRC's ``.hif``
        files, the game's own ``repository.json``), so nothing may go without
        being ticked.
        """
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        report = self.controller.validate_neverwinter_nights()
        self.nit_status.set_info(report["message"])
        if not report["count"]:
            QMessageBox.information(
                self, "Validate Neverwinter Nights", report["message"]
            )
            return
        from vaultkeeper.ui.dialogs.validate_nwn import ValidateNwnDialog

        self._validate_dialog = ValidateNwnDialog(report, self.controller, self)
        self._validate_dialog.finished.connect(lambda _r=0: self.refresh())
        self._validate_dialog.show()

    def _on_state_icon_clicked(self, mod_name: str) -> None:
        """Install or uninstall from the row's status icon (VB ``newtopic28``).

        Confirmed first. The icon is a small target next to the one that merely
        selects, and installing a mod by mis-clicking is not a mistake anyone
        would forgive.
        """
        if self.controller is None:
            return
        md = self.controller.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return
        installed = md.installed
        verb = "Uninstall" if installed else "Install"
        if (
            QMessageBox.question(
                self,
                f"{verb} Mod",
                f"{verb} '{mod_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        message = (
            self.controller.uninstall([mod_name])
            if installed
            else self.controller.install([mod_name])
        )
        self.refresh()
        self._select_mod_by_name(mod_name)
        self.nit_status.set_info(message)

    def _on_new_contents_folder(self) -> None:
        """New folder in the selected mod's payload (VB ``MsNewFolder``).

        VB routes this to New Mod when the *mod list* has focus, because a new
        "folder" there is a new mod. Same rule here.
        """
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        if self.focusWidget() is self._tree or self._contents_mod is None:
            self._on_new_mod()
            return
        name, ok = QInputDialog.getText(
            self,
            "New Folder",
            f"Name of the folder to create in '{self._contents_mod}':",
        )
        if not ok or not name.strip():
            return
        result = self.controller.create_mod_folder(self._contents_mod, name)
        self._after_contents_change(result)

    def _on_new_contents_file(self, suffix: str, label: str) -> None:
        """New empty text/rich-text file (VB ``MsNewTextFile`` / ``MsNewRtfFile``)."""
        if self.controller is None or self._contents_mod is None:
            self.nit_status.set_info("Select a mod first.")
            return
        selected = self._contents.selected_file()
        folder = selected[0] if selected else ""
        name, ok = QInputDialog.getText(
            self,
            f"New {label} File",
            f"Name of the {label.lower()} file to create in "
            f"'{folder or self._contents_mod}':",
            text=f"Notes{suffix}",
        )
        if not ok or not name.strip():
            return
        if not name.lower().endswith(suffix):
            name += suffix
        result = self.controller.create_mod_file(self._contents_mod, folder, name)
        self._after_contents_change(result)

    def _after_contents_change(self, result: dict) -> None:
        self.refresh()
        if self._contents_mod is not None:
            md = self.controller.pd.mod_item(self._contents_mod)
            if md is not None:
                self._show_contents(md)
        self.nit_status.set_info(result["message"])

    def _on_check_for_update(self) -> None:
        """Is there a newer Vaultkeeper? (VB ``MsUpdateNow``.)

        VB downloads a 7-Zip and unpacks it over itself. This offers the release
        page instead: replacing a running application's own files is the part of
        a self-updater that goes wrong, and the useful half — *there is a new
        one, here it is* — needs none of that.
        """
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        from PySide6.QtWidgets import QApplication

        self.nit_status.set_info("Checking for a newer version…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            check = self.controller.check_for_update()
        finally:
            QApplication.restoreOverrideCursor()
        self.nit_status.set_info(check.message)

        if not check.available:
            QMessageBox.information(self, "Update Vaultkeeper", check.message)
            return
        notes = f"\n\n{check.notes[:600]}" if check.notes else ""
        if (
            QMessageBox.question(
                self,
                "Update Vaultkeeper",
                f"{check.message}{notes}\n\nOpen the download page?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self._open_url(check.url)

    def _on_check_web_menu_links(self) -> None:
        """Check the Web menu's addresses (VB ``MsResetWebMenu``).

        VB re-fetches the favicon beside each entry and validates the ones it
        could not get. This menu uses one generic icon, so there is nothing to
        re-fetch and the validation is the whole of it.
        """
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.controller.check_web_menu_links(
                on_progress=lambda done, total, text: (
                    self.nit_status.set_info(f"Checking {text}…"),
                    QApplication.processEvents(),
                )
            )
        finally:
            QApplication.restoreOverrideCursor()
        self.nit_status.set_info(result["message"])

        if result["ok"]:
            QMessageBox.information(self, "Reset Web Menu Icons", result["message"])
            return
        listing = "\n".join(
            f"  {bad['text']} — {bad['problem']}" for bad in result["bad"]
        )
        if (
            QMessageBox.question(
                self,
                "Reset Web Menu Icons",
                f"{result['message']}\n\n{listing}\n\nOpen the Web Menu settings "
                "to fix them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self._on_settings(start_tab="Web Menu")

    def _on_customise_toolbar(self) -> None:
        """Edit the quick toolbar (VB ``MsCustomise`` / the Toolbar Editor)."""
        from vaultkeeper.config.settings import load_settings, save_settings
        from vaultkeeper.ui.dialogs.toolbar_editor import ToolbarEditor
        from vaultkeeper.ui.quick_toolbar import items_from_settings, items_to_settings

        settings = load_settings()
        dialog = ToolbarEditor(
            items_from_settings(settings.quick_toolbar_items),
            self._toolbar_candidates(),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        items = dialog.items()
        settings.quick_toolbar_items = items_to_settings(items)
        save_settings(settings)
        # No reconnect: action_triggered belongs to the toolbar, not to the
        # buttons, so it survives a rebuild — connecting again fires twice.
        self.quick_toolbar.populate(items)
        self._apply_command_availability()
        self.nit_status.set_info("Toolbar saved.")

    def _toolbar_candidates(self) -> list:
        """Menu commands worth offering as toolbar buttons.

        Only ones with an icon and a working handler: the toolbar shows icons —
        and can be set to show *only* icons — so a command with no image is a
        blank square, and a greyed one is a button that does nothing.
        """
        from vaultkeeper.ui.menu_bar import MENUS
        from vaultkeeper.ui.quick_toolbar import ToolItem

        implemented = self.implemented_commands()
        seen: set[str] = set()
        out: list[ToolItem] = []
        for _title, _menu_id, items in MENUS:
            for item in items:
                if not item.action or not item.image or item.action in seen:
                    continue
                if item.action not in implemented:
                    continue
                seen.add(item.action)
                out.append(
                    ToolItem(item.action, item.image, item.caption.replace("&", ""))
                )
        return out

    def _on_update_ee_files(self) -> None:
        """Re-learn what the Enhanced Edition ships (VB ``MsUpdateEeFiles``).

        Run it after Beamdog or Steam patches the game: until then every file the
        patch touched looks like a file some mod changed, and the base-game
        restorers quietly stop recognising half the game.
        """
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        from PySide6.QtWidgets import QApplication

        self.nit_status.set_info("Checking the Enhanced Edition's files…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.controller.update_ee_files(
                on_progress=lambda folder: (
                    self.nit_status.set_info(f"Checking {folder}…"),
                    QApplication.processEvents(),
                )
            )
        finally:
            QApplication.restoreOverrideCursor()
        self.nit_status.set_info(result["message"])

        if not (result["added"] or result["changed"]):
            QMessageBox.information(self, "Update Enhanced Edition Files", result["message"])
            return
        # VB only asks this when the core restorer exists, because otherwise
        # there is nothing the answer could affect.
        if not self.controller.core_files_restorer_exists():
            QMessageBox.information(self, "Update Enhanced Edition Files", result["message"])
            return
        if (
            QMessageBox.question(
                self,
                "Update Enhanced Edition Files",
                result["message"]
                + "\n\nYou have base-game restorers, and they were built from the "
                "old files. Update them now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        ):
            outcome = self.controller.create_original_restorers()
            self.refresh()
            self.nit_status.set_info(outcome.get("message", result["message"]))

    def _on_refresh_workshop_files(self) -> None:
        """Re-check Steam's subscriptions against ours (VB ``MsRefreshWorkshopFiles``).

        The Workshop viewer does this on opening; the menu item is for when you
        have just subscribed to something and do not want the whole screen.
        """
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        from PySide6.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            diff = self.controller.workshop_refresh()
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh()
        self.nit_status.set_info(diff["summary"])

    def _on_send_diagnostics(self) -> None:
        """Gather what a bug report needs (VB ``MsSendDiagInfo``).

        VB opens an email with a diagnostic file to paste in. This writes the
        same information to a file, copies the summary to the clipboard and
        offers the issue tracker — the same substitution already made for Send
        Feedback, and for the same reason: an email address is not something
        this project has, and a mail client is not something every machine does.
        """
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        report = self.controller.diagnostic_report()
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(report["text"])
        self.nit_status.set_info(
            f"Diagnostic information written to {report['path']} and copied to the "
            "clipboard."
        )
        from vaultkeeper.ui.dialogs.text_viewer import TextViewer

        self._diagnostics = TextViewer.show_text(
            report["text"], "Diagnostic Information", self
        )
        if (
            QMessageBox.question(
                self,
                "Send Diagnostic Information",
                "This is what a bug report needs: your versions, your paths and "
                "the recent log.\n\nIt is on the clipboard and saved to\n"
                f"{report['path']}\n\nOpen a new issue now? You can paste it "
                "straight in.\n\nRead it first if you would rather not share a "
                "path or a profile name.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        ):
            from vaultkeeper.ui.feedback import feedback_url

            self._open_url(feedback_url())

    def _on_remove_illegal_files(self) -> None:
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        result = self.controller.remove_illegal_mod_files()
        self.refresh()
        self.nit_status.set_info(result["message"])

    def _on_command_right_clicked(self, action_id: str) -> None:
        """A command's right-click alternate (VB ``Rbn*``/``Ms*_MouseUp``).

        Each of these opens the screen the command is *about* rather than the
        one it does: right-clicking Play opens the Start Screen Manager, because
        the start screen is the thing you see when you play.
        """
        if self.controller is None:
            return
        alternates = {
            "RbnPlay": self._on_loadscreens,
            "RbnPortraitManager": self._on_portrait_web_page,
            "MsPortraitManager": self._on_portrait_web_page,
        }
        handler = alternates.get(action_id)
        if handler is not None:
            handler()

    def _on_portrait_web_page(self) -> None:
        """Open the site portraits are sourced from (VB ``MsPortraitManager`` right-click).

        Silent when no site is configured, which is how VB treats it — the
        setting existed here and nothing had ever read it.
        """
        page = self.controller._settings().portrait_image_web_page.strip()
        if page:
            self._open_url(page)
        else:
            self.nit_status.set_info(
                "No portrait image web page is set (Settings → Character / Save Viewer)."
            )

    # -- Options-menu housekeeping (VB Options menu) ------------------------ #
    def _on_reset_window_layout(self) -> None:
        """Put the window and its panels back to their defaults (VB ``MsResetWindow``).

        Both halves matter: forgetting the saved geometry alone leaves the
        splitters wherever they were dragged, which is usually the thing that
        went wrong.
        """
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings()
        settings.window_geometry = ""
        # Every remembered dialog size goes too. A remembered size can itself be
        # the thing that is wrong — a screen dragged onto a monitor that is not
        # there any more — and this is the only way back from one.
        settings.dialog_geometry = {}
        save_settings(settings)
        self.resize(1200, 760)
        for splitter in self._splitters:
            # Equal shares, then the stretch factors reassert the intended
            # proportions on the next layout pass.
            count = splitter.count()
            if count:
                splitter.setSizes([1] * count)
        self.nit_status.set_info("Window layout reset.")

    def _selected_contents_file(self) -> tuple[str, str, str] | None:
        """``(mod, folder, filename)`` for the Contents selection, if there is one."""
        selected = self._contents.selected_file()
        if self.controller is None or self._contents_mod is None or selected is None:
            return None
        folder, filename = selected
        return self._contents_mod, folder, filename

    def _on_move_to_folder(self) -> None:
        """Move the selected file to its other mapped folder (VB ``MsMoveToFolder``).

        The mapper keeps a second folder per extension — a ``.hak`` can live in
        ``hak`` or ``patch``, a ``.tga`` in its own folder or ``override`` — and
        this toggles between them.
        """
        picked = self._selected_contents_file()
        if picked is None:
            self.nit_status.set_info("Select a file in Contents first.")
            return
        mod, folder, filename = picked
        target = self.controller.move_target_folder(mod, folder, filename)
        if not target:
            self.nit_status.set_info(f"{filename} has no other folder to move to.")
            return
        result = self.controller.move_mod_files(mod, folder, [filename], target)
        self._after_contents_move(mod, result)

    def _on_move_to_history(self) -> None:
        """Keep the old version of a file (VB ``MsMoveToHistory``)."""
        picked = self._selected_contents_file()
        if picked is None:
            self.nit_status.set_info("Select a file in Contents first.")
            return
        mod, folder, filename = picked
        result = self.controller.move_mod_files_to_history(mod, folder, [filename])
        self._after_contents_move(mod, result)

    def _after_contents_move(self, mod: str, result: dict) -> None:
        self.refresh()
        md = self.controller.pd.mod_item(mod)
        if md is not None:
            self._show_contents(md)
        self.nit_status.set_info(result["message"])

    def _on_view_clipboard(self) -> None:
        """Show what is on the clipboard (VB ``MsViewClipboard``).

        Several commands here put things on it — a mod name, a DebugMode
        command, a level summary — and this is how you check what landed.
        """
        from PySide6.QtWidgets import QApplication

        from vaultkeeper.ui.dialogs.text_viewer import TextViewer

        text = QApplication.clipboard().text()
        self._clipboard_viewer = TextViewer.show_text(
            text or "(the clipboard holds no text)", "Clipboard", self
        )

    def _on_clear_wait_cursors(self) -> None:
        """Release any stuck busy cursor (VB ``MsClearWaitCursors``).

        An override cursor that outlives the work it belonged to leaves the whole
        application looking hung when it is not. This is the escape hatch.
        """
        from PySide6.QtWidgets import QApplication

        cleared = 0
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
            cleared += 1
            if cleared > 32:  # a runaway stack is a bug, not a reason to hang here
                break
        self.nit_status.set_info(
            f"Cleared {cleared} wait cursor(s)." if cleared else "No wait cursor was set."
        )

    def _on_clear_selection_history(self) -> None:
        """Forget what was selected in each mod (VB ``MsClearSelectionHistory``).

        ``newtopic63.htm``: "delete Mod selection information for the Contents
        Panel and Details Panel". This used to clear the *Recent Mods* list,
        which is a different list reached by a different command — an easy
        confusion, since both are called history.
        """
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings()
        count = len(settings.contents_selection)
        settings.contents_selection = {}
        save_settings(settings)
        self.nit_status.set_info(
            f"Cleared the remembered selection for {count:,} mod(s)."
        )

    def _on_open_recycle_bin(self) -> None:
        """Open the OS trash (VB ``BtRecycleToggle`` right-click → explorer)."""
        import subprocess
        import sys
        from pathlib import Path

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(Path.home() / ".Trash")])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"])
            else:
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(Path.home() / ".local/share/Trash/files"))
                )
        except OSError:
            log.exception("Could not open the recycle bin")
            self.nit_status.set_info("Could not open the Recycle Bin / Trash.")

    def _on_create_restorer(self) -> None:
        """Create a Restorer (VB ``MsCreateRestorer``).

        VB offers "Create NWN character Restorer" inside the naming dialog, and
        only when there are character files no mod owns. Same rule here: those
        are offered first, because having just finished a game is when this is
        wanted and a mod need not be selected for it.
        """
        if self.controller is None:
            return
        if self._offer_character_restorer():
            return
        names = self.selected_mod_names()
        if not names:
            self.nit_status.set_info("Select a mod first.")
            return
        made = sum(1 for n in names if self.controller.create_restorer(n))
        self.refresh()
        self.nit_status.set_info(f"Created restorer for {made} mod(s).")

    def _offer_character_restorer(self) -> bool:
        """Offer to save unowned characters; True when that is what happened."""
        from PySide6.QtWidgets import QMessageBox

        groups = self.controller.unowned_characters()
        if not groups:
            return False
        total = sum(g.count for g in groups)
        answer = QMessageBox.question(
            self,
            "Create Restorer",
            f"{total} character file(s) in your game belong to no mod.\n\n"
            "Create a Character Restorer to keep those builds?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False  # fall through to the ordinary selection-based restorer

        from vaultkeeper.ui.dialogs.character_restorer import CharacterRestorerDialog

        prefix = self.controller._settings().character_restorer_prefix
        dialog = CharacterRestorerDialog(groups, prefix, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return True  # asked and answered: do not also do the other thing
        created = files = 0
        problems = []
        for name, keys in dialog.chosen():
            result = self.controller.create_character_restorer(name, keys)
            if result["ok"]:
                created += 1
                files += result["files"]
            else:
                problems.append(result["message"])
        self.refresh()
        message = f"Created {created} character restorer(s) ({files} file(s))."
        if problems:
            message = f"{message} {problems[0]}"
        self.nit_status.set_info(message if created or problems else "Nothing created.")
        return True

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
        """Move the selected mods to a group, or out of all of them.

        ``movingmodsfromonegrouptoanother.htm``: "You can also click **None**
        from the Group drop down list if you want to ungroup the selected Mods."
        Typing "None" used to make a group actually called None, which is a
        different and permanent thing.
        """
        from vaultkeeper.core import constants as C

        names = self.selected_mod_names()
        if self.controller is None or not names:
            return
        existing = [
            g
            for g in self.controller.group_names()
            if not g.startswith(C.GROUP_HIDDEN_PREFIX)
        ]
        group, ok = QInputDialog.getItem(
            self,
            "Move to Group",
            "Target group:\n(None leaves them ungrouped — ungrouped mods sort "
            "first, so they lose every file conflict.)",
            ["None", *existing],
            0,
            editable=True,
        )
        if not ok or not group.strip():
            return
        target = group.strip()
        self.controller.move_to_group(names, C.GROUP_NONE if target == "None" else target)
        self.refresh()
        self.nit_status.set_info(
            f"Moved {len(names)} mod(s) "
            + ("out of their group." if target == "None" else f"to '{target}'.")
        )

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

        self._character_viewer = CharacterViewer.show_for(
            self.controller,
            self,
            # VB closes the Explorer and opens the Portrait Manager when the
            # portrait is clicked (PicPortrait_Click / CmOpenPortraitManager).
            on_open_portrait_manager=lambda _resref: self._on_portraits(),
            # Select closes the Explorer on the mod the character belongs to,
            # which is the thing you go on to install or play.
            on_select=self._select_mod_by_name,
        )


    def _on_save_game_editor(self) -> None:
        if self.controller is None:
            return
        from nwnsaveeditor.ui.editor.window import SaveEditorWindow

        self._save_game_editor = SaveEditorWindow.show_for(self.controller, self)

    def _on_portraits(self) -> None:
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager

        self._portrait_manager = PortraitManager.show_for(
            self.controller, self._select_mod_by_name, self
        )

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

        self._mod_play_viewer = ModPlayViewer.show_for(
            self.controller,
            self,
            on_select=self._select_mod_by_name,
            on_add_recent=self._record_recent_mod,
        )

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

        self._analyser = InstallationAnalyser.show_for(
            self.controller, self._select_mod_by_name, self
        )

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

        self._mod_explorer = ModExplorer.show_for(
            self.controller,
            self._select_mod_by_name,
            self,
            # The recent list lives on the window, so the dialog is given a way
            # in rather than a reference to it (VB CmAddToRecentMods).
            on_add_recent=self._record_recent_mod,
        )

    def _on_backup_manager(self) -> None:
        """Open the Backup and Export Manager (VB ``MsBackupManager``)."""
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.backup_manager import BackupManager

        self._backup_manager = BackupManager.show_for(self.controller, self)

    def _on_backup_data(self) -> None:
        if self.controller is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Backup Data", "vaultkeeper-backup.zip", "Zip archives (*.zip)"
        )
        if path:
            from pathlib import Path

            self.nit_status.set_info(self.controller.backup_data(Path(path)))

    def _on_export_settings(self) -> None:
        """Write the current preferences to the store (VB RbnExportSettings_Click).

        The geometry is folded in first, exactly as VB saves the window and panel
        layout into the settings before exporting: otherwise the export captures
        the app as it was last persisted rather than as it stands now, which is
        the opposite of what somebody pressing "export" is asking for.
        """
        if self.controller is None:
            return
        self._save_geometry()
        result = self.controller.export_settings()
        self.nit_status.set_info(result["message"])
        if not result["ok"]:
            QMessageBox.warning(self, "Export Settings", result["message"])

    def _on_import_settings(self) -> None:
        """Load a previously exported settings file (the counterpart to export)."""
        if self.controller is None:
            return
        exported = self.controller.exported_settings_files()
        start = str(exported[0].parent) if exported else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", start, "Exported settings (*.json);;All files (*)"
        )
        if not path:
            return
        from pathlib import Path

        if (
            QMessageBox.question(
                self,
                "Import Settings",
                "Replace your current preferences with this file?\n\nYour game "
                "folders, store location and active profile are kept — those "
                "describe this machine, not your preferences.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self.controller.import_settings(Path(path))
        self.nit_status.set_info(result["message"])
        if not result["ok"]:
            QMessageBox.warning(self, "Import Settings", result["message"])

    def _on_export_mods(self) -> None:
        """Write the selected mods out as .vkmod archives (VB MsExportMods)."""
        if self.controller is None:
            return
        names = self.selected_mod_names()
        if not names:
            QMessageBox.information(
                self, "Export Mods", "Select the mods you want to export first."
            )
            return
        # Offered against the store's own Exported Mods folder, which is where
        # the Backup and Export Manager looks. Somewhere else is still fine —
        # it just will not be listed there afterwards.
        default = self.controller.exported_mods_dir()
        default.mkdir(parents=True, exist_ok=True)
        folder = QFileDialog.getExistingDirectory(
            self, "Export the selected mods to", str(default)
        )
        if not folder:
            return

        # Asked, not assumed: _Downloads is usually the bulk of a mod, and
        # whether the other machine needs it depends on whether it will rebuild
        # the installer or just install it.
        answer = QMessageBox.question(
            self,
            "Export Mods",
            "Include each mod's _Downloads folder?\n\nThe original archives are "
            "only needed to rebuild an installer, and are usually much larger "
            "than everything else in the mod.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return

        from pathlib import Path

        result = self.controller.export_mods(
            names,
            Path(folder),
            include_downloads=answer == QMessageBox.StandardButton.Yes,
        )
        self.nit_status.set_info(result["message"])

    def _on_import_mods(self) -> None:
        """Bring exported mods into this profile (VB MsImportMods)."""
        if self.controller is None:
            return
        from vaultkeeper.game.mod_transfer import SUFFIX

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Mods", "", f"Exported mods (*{SUFFIX});;All files (*)"
        )
        if not paths:
            return
        from pathlib import Path

        result = self.controller.import_mods([Path(p) for p in paths])
        self.refresh()
        self.nit_status.set_info(result["message"])
        if result["failed"]:
            QMessageBox.warning(
                self,
                "Import Mods",
                "These could not be imported:\n\n"
                + "\n".join(f"{name} — {why}" for name, why in result["failed"]),
            )

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

    def _on_prc_module(self) -> None:
        """Install a Vault module rebuilt for PRC, from the published Drive folder."""
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.prc_module import PrcModuleDialog

        self._prc_dialog = PrcModuleDialog(self.controller, parent=self)
        # Installing creates mods (the module and each dependency), so the list
        # is stale by the time the dialog closes.
        self._prc_dialog.finished.connect(self.refresh)
        self._prc_dialog.show()

    def _on_basic_settings(self) -> None:
        """Open the curated Basic Settings dialog (VB BasicSettings).

        Its **Advanced** button chains into the full Settings browser, matching VB
        ``BtAdvanced`` (``DialogResult.Yes`` → ``MsSettings.PerformClick``).
        """
        from vaultkeeper.ui.dialogs.basic_settings import BasicSettingsDialog

        settings, advanced = BasicSettingsDialog.edit(parent=self)
        if settings is not None:
            self._apply_basic_settings(settings)
            self.nit_status.set_info("Settings saved.")
        if advanced:
            self._on_settings()

    def _apply_basic_settings(self, settings) -> None:  # noqa: ANN001
        """Apply the live effects of a settings change (splitter width + appearance)."""
        self._apply_splitter_width(settings.splitter_width)
        from PySide6.QtWidgets import QApplication

        from vaultkeeper.ui.theme import apply_appearance

        app = QApplication.instance()
        if app is not None:
            apply_appearance(
                app,
                font_point_size=settings.font_point_size,
                theme=settings.theme,
                font_family=settings.font_family,
            )
        # The mod list takes its row colours as brushes when it is populated, so
        # a new palette does not reach rows that already exist. Repopulating is
        # what makes a theme change visible without a restart.
        if self.controller is not None:
            self.refresh()

    def _apply_splitter_width(self, width: int) -> None:
        """Set the drag-handle thickness on the window's splitters (VB SplitterWidth)."""
        from PySide6.QtWidgets import QSplitter

        handle = max(1, int(width)) * 2 + 1
        for splitter in self.findChildren(QSplitter):
            splitter.setHandleWidth(handle)

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
            # Appearance too. This used to be applied only by Basic Settings, so
            # changing the theme in Advanced Settings did nothing until the app
            # was restarted — which is what the owner saw.
            self._apply_basic_settings(settings)
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
            # Vaultkeeper's own two files. Both were on the View menu and greyed
            # out, which is an odd thing for "show me this file" to be when the
            # file is right there.
            "MsDisplaySettings": (
                self.controller.settings_file_path(), "Vaultkeeper User Config File"
            ),
            "MsOpenRulesFile": (
                self.controller.download_rules_path(), "Download Rules File"
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
        if not toolset:
            self._apply_play_preferences()

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
            # Say which one is missing. Enhanced Edition ships the toolset on
            # Windows only, so on macOS and Linux this is the expected answer
            # for a perfectly good install — reporting the *game* as not found
            # would send someone looking for a problem that is not there.
            self.nit_status.set_info(
                "The Neverwinter Nights toolset was not found in this install "
                "(Enhanced Edition includes it on Windows only)."
                if toolset
                else "Neverwinter Nights install not found."
            )
            return
        if QProcess.startDetached(argv[0], argv[1:]):
            self.nit_status.set_info(f"Launched {what}.")
        else:
            self.nit_status.set_info(f"Could not launch {what}.")

    def _apply_play_preferences(self) -> None:
        """The three "when you press Play" preferences (VB ``MsPlayNeverwinterNights``).

        All three were settings the port stored, offered in two screens and
        never read, so ticking any of them did nothing at all.
        """
        from PySide6.QtWidgets import QApplication

        settings = self.controller._settings()
        loop = self.controller.play_loop
        current_mod = loop.current_play_title()[0] if loop is not None else ""

        # Select the mod the current game belongs to (VB BehaviourSelectGameMod).
        if settings.select_game_mod and current_mod:
            self._select_mod_by_name(current_mod)

        # The DebugMode console command, ready to paste in-game (VB
        # ConfigCopyDebugModeOnPlay). VB will not overwrite a clipboard that
        # already holds a dm_ command, so neither does this.
        clipboard = QApplication.clipboard()
        if settings.copy_debug_mode_on_play:
            try:
                if "dm_" not in (clipboard.text() or ""):
                    clipboard.setText(settings.copy_debug_mode_on_play.split("(")[0].strip())
            except Exception:
                log.exception("Could not copy the DebugMode command")

        # The selected mod's name, for typing into the new-game screen (VB
        # ConfigCopyOnPlay). Only when there is *no* game in progress and one
        # mod is selected — starting a new game is the case it exists for.
        if settings.copy_mod_name_on_play and not current_mod:
            names = self.selected_mod_names()
            if len(names) == 1:
                try:
                    clipboard.setText(names[0])
                except Exception:
                    log.exception("Could not copy the mod name")

    def _on_game_exited(self) -> None:
        """Process a finished play session (VB post-play exit processing)."""
        from datetime import datetime

        started = getattr(self, "_play_started", None)
        self._game_process = None
        if self.controller is None or started is None:
            return
        summary = self.controller.process_play_session(started, datetime.now())
        note = self._auto_character_restorer(summary)
        self.refresh()
        mods = summary.get("mods", {})
        if mods:
            names = ", ".join(sorted(mods))
            self.nit_status.set_info(f"Recorded play time for: {names}.{note}")
        else:
            self.nit_status.set_info(f"Finished playing (no play time recorded).{note}")

    def _auto_character_restorer(self, summary: dict) -> str:
        """Save the character just played, when asked to (VB ``BehaviourAutoCharacter``).

        Only when there is one character with no owner — several is a question
        about which belongs to what, and a question is not something to ask
        somebody who has just closed the game.
        """
        if not self.controller._settings().auto_character:
            return ""
        played = next(iter(sorted(summary.get("mods", {}))), "")
        try:
            result = self.controller.auto_character_restorers(played)
        except Exception:
            log.exception("Could not create a character restorer")
            return ""
        return f" {result['message']}" if result.get("created") else ""

    def _not_implemented(self) -> None:
        self.nit_status.set_info("That command is not available yet.")

    def _on_mod_double_clicked(self, item, _column: int = 0) -> None:
        """Install the double-clicked mod, or uninstall it (VB ``FvMods``).

        Whichever of Install/Uninstall is the one currently offered — the same
        test the buttons use, so a double-click can never do something the
        toolbar would refuse. A group header is left to expand and collapse.
        """
        if self.controller is None or item is None:
            return
        if not self._tree.mod_name_of(item):
            return  # a group header: Qt's expand/collapse is the right action
        if self._act_install.isEnabled():
            self._on_install()
        elif self._act_uninstall.isEnabled():
            self._on_uninstall()

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

    def _on_mod_info_link(self, href: str) -> None:
        """The mod summary's link: open the page, or offer to record one."""
        if href == "vaultkeeper:add-link":
            self._on_edit_web_link()
            return
        self._open_url(href)

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

    def _on_find_web_link(self) -> None:
        """Find the selected mod's Vault page (VB ``MsFindWebLink``).

        Identified by the files the mod already holds, not by its name. One match
        is offered for saving; several are offered as a choice, because the wrong
        page attaches the wrong prerequisites to everything downstream.
        """
        names = self.selected_mod_names()
        if self.controller is None or len(names) != 1:
            self.nit_status.set_info("Select a single mod first.")
            return
        mod = names[0]
        from PySide6.QtWidgets import QApplication

        self.nit_status.set_info(f"Searching the Neverwinter Vault for '{mod}'…")
        # A handful of requests, not a pass over the whole store — short enough
        # to wait for, long enough that the pointer should say so.
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            result = self.controller.find_mod_web_link(mod)
        finally:
            QApplication.restoreOverrideCursor()
        self.nit_status.set_info(result["message"])
        if not result["ok"]:
            QMessageBox.information(self, "Find Mod's Web Page Link", result["message"])
            return

        candidates = result["candidates"]
        chosen = candidates[0]
        if len(candidates) > 1:
            labels = [f"{c.title} — {c.url}" for c in candidates]
            label, ok = QInputDialog.getItem(
                self,
                "Find Mod's Web Page Link",
                f"{len(candidates)} Vault pages publish a file '{mod}' holds.\n"
                "Choose the right one:",
                labels,
                0,
                False,
            )
            if not ok:
                return
            chosen = candidates[labels.index(label)]

        current = self.controller.mod_web_link(mod)
        question = (
            f"{chosen.title}\n{chosen.url}\n\nSave this as '{mod}'s web page link?"
        )
        if current and current != chosen.url:
            question = f"{chosen.title}\n{chosen.url}\n\nReplace:\n{current}"
        answer = QMessageBox.question(
            self,
            "Find Mod's Web Page Link",
            question,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Open
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Open:
            self._open_url(chosen.url)
            return
        if answer != QMessageBox.StandardButton.Save:
            return
        saved = self.controller.set_mod_web_link(mod, chosen.url)
        self.nit_status.set_info(saved["message"])
        md = self.controller.pd.mod_item(mod)
        if md is not None:
            self._show_details(md)

    def _on_check_for_mod_updates(self) -> None:
        """Open the selected mod's Vault page in Download Project (VB ``MsCheckForUpdates``).

        The way to know whether a mod has a newer file is to look at what its
        project publishes now and compare it with what was downloaded — so this
        is Download Project, opened on the mod's own link and already fetched.
        """
        names = self.selected_mod_names()
        if self.controller is None or len(names) != 1:
            self.nit_status.set_info("Select a single mod first.")
            return
        mod = names[0]
        link = self.controller.mod_web_link(mod)
        if not link:
            self.nit_status.set_info(
                f"'{mod}' has no web page link — use Find Mod's Web Page Link first."
            )
            return
        from vaultkeeper.ui.dialogs.download_project import DownloadProjectDialog

        self._download_dialog = DownloadProjectDialog(
            self.controller, default_mod=mod, parent=self
        )
        self._download_dialog.finished.connect(self.refresh)
        self._download_dialog.show()
        self._download_dialog.url_edit.setText(link)
        self._download_dialog._on_fetch()

    def _on_validate_mod_web_links(self) -> None:
        """Check every mod's Vault link and report (VB ``MsValidateModWebLinks``)."""
        if self.controller is None:
            self.nit_status.set_info("Set up a profile first.")
            return
        from vaultkeeper.ui.dialogs.mod_links_report import ModLinksReportDialog

        self._links_report = ModLinksReportDialog.show_for(self.controller, self)

    def _on_find(self) -> None:
        """Find, in whichever pane has focus (VB ``MsFind``).

        One command, three meanings — "the scope of the search operation depends
        on which element in the UI has focus". Clicking a mod name searches the
        whole profile; clicking in the contents or properties list steps through
        its rows; clicking in the notes searches the text. Always opening the
        profile search, as this used to, makes the other two unreachable.
        """
        # self.focusWidget(), not QApplication.focusWidget(): the former answers
        # for this window whether or not the window is the active one, which is
        # both more accurate here and testable without a window manager.
        focus = self.focusWidget()
        for pane in (self._details, self._contents, self._details_list):
            if focus is pane or (focus is not None and focus.parent() is pane):
                from vaultkeeper.ui.dialogs.find_text import FindTextDialog

                self._find_text_dialog = FindTextDialog(pane, self)
                self._find_text_dialog.show()
                return

        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.find_files import FindFilesDialog

        self._find_dialog = FindFilesDialog.show_for(
            self.controller, self._select_mod_by_name, self
        )

    def _on_find_and_rename(self) -> None:
        """Open the bulk find/replace-across-mod-names dialog (VB ``MsFindAndRename``)."""
        if self.controller is None:
            return
        from vaultkeeper.ui.dialogs.find_and_rename import FindAndRenameDialog

        self._find_rename_dialog = FindAndRenameDialog.show_for(
            self.controller,
            self._on_renames_applied,
            self,
            # "The Mod names that match your Find criteria are selected in the
            # Mod list" — the preview shows what would change, the selection
            # shows which mods.
            on_found=self._tree.select_mods,
        )

    def _on_renames_applied(self, _report: dict) -> None:
        """Refresh the mod list after a bulk rename (VB reselect + refresh)."""
        self.refresh()

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
        if self.controller is None:
            return
        names = self.selected_mod_names()
        if not names:
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

    def _on_delete_groups(self, groups: list[str]) -> None:
        """Delete the selected groups and their member mods (VB DeleteSelectedGroups)."""
        if self.controller is None:
            return
        members = sum(len(self.controller.group_member_names(g)) for g in groups)
        prompt = (
            f"Delete {len(groups)} group(s)?\n"
            f"NOTE: all {members} mod(s) belonging to the selected group(s) will "
            "also be removed from the profile (installed mods are uninstalled first)."
        )
        if not self._confirm("Delete Groups", prompt):
            return
        report = self.controller.delete_groups(groups)
        self.refresh()
        removed = len(report["removed_groups"])
        failed = len(report["failed_groups"])
        if failed:
            self.nit_status.set_info(
                f"Deleted {removed} group(s); {failed} could not be removed."
            )
        else:
            self.nit_status.set_info(
                f"Deleted {removed} group(s) and {report['deleted_mods']} mod(s)."
            )
