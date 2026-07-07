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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.file_view import FileView
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

        self._contents = QTreeWidget()
        self._contents.setHeaderLabels(["Contents"])
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
        self.nit_status.set_info("Ready")

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
            "<p>Use <b>File &rarr; Set Up Profile…</b> to locate your Neverwinter "
            "Nights folder and create a profile.</p>"
        )
        self.nit_status.set_info("No profile — use File ▸ Set Up Profile…")

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
        for act in (self._act_install, self._act_uninstall, self._act_rename, self._act_remove):
            if act is not None:
                act.setEnabled(False)

        # The ribbon/toolbar visibility toggles start checked (both shown).
        for item_id in ("MsShowRibbon", "MsShowToolbar"):
            act = self.nit_menu.action(item_id)
            if act is not None:
                act.setChecked(True)

    def _on_toggle(self, item_id: str, checked: bool) -> None:
        """Handle checkable menu items (VB check-on-click toggles)."""
        if item_id == "MsShowRibbon":
            self.ribbon.setVisible(checked)
        elif item_id == "MsShowToolbar":
            self.quick_toolbar.setVisible(checked)

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
        menu.exec(QCursor.pos())

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
        self._update_status()

    def _update_status(self) -> None:
        if self.controller is None:
            return
        total, installed = self.controller.counts()
        # Real status segments (VB BtModCount) instead of an overlaying message.
        self.nit_status.set_mod_count(installed, total)

    # -- Selection / actions ---------------------------------------------- #
    def selected_mod_names(self) -> list[str]:
        return self._tree.selected_mod_names()

    def _on_selection_changed(self, names: list[str] | None = None) -> None:
        if names is None:
            names = self.selected_mod_names()
        has_sel = bool(names)
        self._act_install.setEnabled(has_sel)
        self._act_uninstall.setEnabled(has_sel)
        self._act_remove.setEnabled(has_sel)
        self._act_rename.setEnabled(len(names) == 1)  # rename one at a time
        if self.controller is not None and len(names) == 1:
            md = self.controller.pd.mod_item(names[0])
            if md is not None:
                self._show_details(md)
                self._show_contents(md)
        else:
            self._save_current_notes()
            self._notes_mod = None
            self._contents.clear()
            self._details_list.clear()
            self._details.clear()
            self._mod_info.setText("")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Persist any unsaved mod notes before closing."""
        self._save_current_notes()
        super().closeEvent(event)

    def _show_contents(self, md: ModData) -> None:
        """Show the selected mod's installer files, grouped by folder."""
        self._contents.clear()
        by_folder: dict[str, list[str]] = {}
        for fk in md.files:
            by_folder.setdefault(fk.folder, []).append(fk.filename)
        for folder in sorted(by_folder):
            folder_item = QTreeWidgetItem([folder])
            self._contents.addTopLevelItem(folder_item)
            for filename in sorted(by_folder[folder]):
                folder_item.addChild(QTreeWidgetItem([filename]))
            folder_item.setExpanded(True)

    def _show_details(self, md: ModData) -> None:
        # Details list (VB FvDetails): key properties as Property/Value rows.
        rows: list[tuple[str, str]] = [
            ("Group", md.group),
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
        """Persist the currently-loaded mod's notes if the user edited them."""
        if (
            self.controller is not None
            and self._notes_mod is not None
            and self._details.document().isModified()
        ):
            self.controller.save_notes(self._notes_mod, self._details.toPlainText())
            self._details.document().setModified(False)

    # -- Ribbon / toolbar dispatch ----------------------------------------- #
    def _on_command(self, action: str) -> None:
        """Route a ribbon/toolbar action id to its handler (VB Handles subs).

        Actions already implemented in this phase are wired to their handlers;
        the rest report "not yet available" so the chrome is fully clickable while
        later phases fill in the remaining commands.
        """
        handlers = {
            # Install / uninstall (ribbon, toolbar, menu).
            "TsInstall": self._on_install,
            "RbnInstallUninstall": self._on_install,
            "MsInstall": self._on_install,
            "TsUninstall": self._on_uninstall,
            "MsUninstall": self._on_uninstall,
            # Rename / remove.
            "TsRename": self._on_rename,
            "MsRename": self._on_rename,
            "TsDelete": self._on_remove,
            "MsDelete": self._on_remove,
            # Groups.
            "MsNewGroup": self._on_new_group,
            "TsNewGroup": self._on_new_group,
            "MsMoveToGroup": self._on_move_to_group,
            "TsMoveToGroup": self._on_move_to_group,
            # Engine maintenance.
            "MsAnneal": self._on_anneal,
            # Play loop.
            "MsGameSaves": self._on_game_saves,
            "TsGameSaves": self._on_game_saves,
            "RbnGameSaves": self._on_game_saves,
            "MsPlayNeverwinterNights": self._on_play,
            "TsPlayNeverwinterNights": self._on_play,
            "RbnPlay": self._on_play,
            "MsToolset": lambda: self._on_play(toolset=True),
            "RbnToolset": lambda: self._on_play(toolset=True),
            # View / selection.
            "MsSelectAll": self._on_select_all,
            "TsSelectAll": self._on_select_all,
            "MsCollapseAllGroups": self._tree.collapseAll,
            "MsExpandAllGroups": self._tree.expandAll,
            # Profile lifecycle.
            "MsLoadProfile": self._on_setup,
            "MsOpen": self._on_setup,
            "MsRestart": self.refresh,
            "MsExit": self.close,
        }
        handler = handlers.get(action, self._not_implemented)
        handler()

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

    def _on_select_all(self) -> None:
        self._tree.selectAll()

    def _on_game_saves(self) -> None:
        if self.controller is None:
            return
        self.nit_status.set_info(self.controller.current_game_summary())

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

    def _on_remove(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            return
        prompt = (
            f"Remove {len(names)} mod(s) from the profile?\n"
            "(The mod files on disk are not deleted.)"
        )
        answer = QMessageBox.question(self, "Remove from Profile", prompt)
        if answer != QMessageBox.StandardButton.Yes:
            return
        removed = self.controller.remove_mods(names)
        self.refresh()
        self.nit_status.set_info(f"Removed {removed} mod(s) from the profile")
