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
        self.setWindowTitle("Vaultkeeper")
        self.setWindowIcon(R.app_icon())
        self.resize(1000, 640)

        self._tree = FileView("Mods")
        self._tree.selection_changed.connect(self._on_selection_changed)

        self._contents = QTreeWidget()
        self._contents.setHeaderLabels(["Contents"])

        self._details = QTextEdit()
        self._details.setReadOnly(True)

        # Three panes: mods | contents | details (mirrors the VB NIT layout).
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._contents)
        splitter.addWidget(self._details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)

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
        self.setStatusBar(self.nit_status)

        self._build_menu()
        self.nit_status.set_info("Ready")

        if controller is not None:
            self.refresh()
        else:
            self._show_empty_state()

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
            self._contents.clear()

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
        lines = [
            f"<h3>{md.mod_name}</h3>",
            f"<b>Group:</b> {md.group}<br>",
            f"<b>State:</b> {md.mod_state.name}<br>",
            f"<b>Files:</b> {len(md.files):,}<br>",
        ]
        if md.web_link:
            lines.append(f"<b>Web:</b> {md.web_link}<br>")
        self._details.setHtml("".join(lines))

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
            # Profile lifecycle.
            "MsLoadProfile": self._on_setup,
            "MsOpen": self._on_setup,
            "MsRestart": self.refresh,
            "MsExit": self.close,
        }
        handler = handlers.get(action, self._not_implemented)
        handler()

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
