"""Vaultkeeper main window (PySide6).

A first functional three-pane manager: a grouped mod tree on the left, a details
panel on the right, a menu bar and a status bar. It is wired to a
:class:`ProfileController`, so selecting mods and choosing Install/Uninstall drives
the real domain engine. The layout deliberately mirrors the VB NIT main form
(mods list | mod details) and grows toward full parity in later phases.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
)

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController

_INSTALLED_BRUSH = QBrush(QColor(0x2E, 0x7D, 0x32))  # green
_OVERRIDDEN_BRUSH = QBrush(QColor(0xB2, 0x6A, 0x00))  # amber
_ROLE_MOD_NAME = Qt.ItemDataRole.UserRole


class MainWindow(QMainWindow):
    """The Vaultkeeper main window."""

    def __init__(self, controller: ProfileController | None = None) -> None:
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Vaultkeeper")
        self.resize(1000, 640)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Mods"])
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)

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
        self.setCentralWidget(splitter)

        self._build_menu()
        self.statusBar().showMessage("Ready")

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
        self.statusBar().showMessage("No profile — use File ▸ Set Up Profile…")

    # -- Menu -------------------------------------------------------------- #
    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        self._act_setup = QAction("&Set Up Profile…", self)
        self._act_setup.triggered.connect(self._on_setup)
        file_menu.addAction(self._act_setup)
        self._act_refresh = QAction("&Refresh", self)
        self._act_refresh.triggered.connect(self.refresh)
        file_menu.addAction(self._act_refresh)
        file_menu.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        mods_menu = menubar.addMenu("&Mods")
        self._act_install = QAction("&Install", self)
        self._act_install.triggered.connect(self._on_install)
        mods_menu.addAction(self._act_install)
        self._act_uninstall = QAction("&Uninstall", self)
        self._act_uninstall.triggered.connect(self._on_uninstall)
        mods_menu.addAction(self._act_uninstall)
        mods_menu.addSeparator()
        self._act_rename = QAction("Re&name…", self)
        self._act_rename.triggered.connect(self._on_rename)
        mods_menu.addAction(self._act_rename)
        self._act_remove = QAction("&Remove from Profile…", self)
        self._act_remove.triggered.connect(self._on_remove)
        mods_menu.addAction(self._act_remove)
        self._act_install.setEnabled(False)
        self._act_uninstall.setEnabled(False)
        self._act_rename.setEnabled(False)
        self._act_remove.setEnabled(False)

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
            self.statusBar().showMessage(f"Note: game config changed ({names})")

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
        self.statusBar().showMessage(f"Profile '{name.strip()}' ready")

    # -- Population -------------------------------------------------------- #
    def refresh(self) -> None:
        """Rebuild the mod tree from the controller's profile."""
        self._tree.clear()
        if self.controller is None:
            return
        for group_name, members in self.controller.groups():
            group_item = QTreeWidgetItem([group_name])
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._tree.addTopLevelItem(group_item)
            for md in members:
                child = QTreeWidgetItem([self._mod_label(md)])
                child.setData(0, _ROLE_MOD_NAME, md.mod_name)
                brush = self._state_brush(md)
                if brush is not None:
                    child.setForeground(0, brush)
                group_item.addChild(child)
            group_item.setExpanded(True)
        self._update_status()

    @staticmethod
    def _mod_label(md: ModData) -> str:
        if md.installed:
            return f"{md.mod_name}  ✓"
        return md.mod_name

    @staticmethod
    def _state_brush(md: ModData) -> QBrush | None:
        if md.mod_state in (State.OVERRIDDEN, State.INSTALLED_AND_OVERRIDDEN):
            return _OVERRIDDEN_BRUSH
        if md.installed:
            return _INSTALLED_BRUSH
        return None

    def _update_status(self) -> None:
        if self.controller is None:
            return
        total, installed = self.controller.counts()
        self.statusBar().showMessage(f"Mods: {total:,}   Installed: {installed:,}")

    # -- Selection / actions ---------------------------------------------- #
    def selected_mod_names(self) -> list[str]:
        names: list[str] = []
        for item in self._tree.selectedItems():
            name = item.data(0, _ROLE_MOD_NAME)
            if name:
                names.append(name)
        return names

    def _on_selection_changed(self) -> None:
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

    def _on_install(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            return
        message = self.controller.install(names)
        self.refresh()
        self.statusBar().showMessage(message or "Install complete")

    def _on_uninstall(self) -> None:
        names = self.selected_mod_names()
        if self.controller is None or not names:
            return
        message = self.controller.uninstall(names)
        self.refresh()
        self.statusBar().showMessage(message or "Uninstall complete")

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
            self.statusBar().showMessage(f"Renamed '{old}' to '{new}'")
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
        self.statusBar().showMessage(f"Removed {removed} mod(s) from the profile")
