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
    QMainWindow,
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

        self._details = QTextEdit()
        self._details.setReadOnly(True)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._details)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self._build_menu()
        self.statusBar().showMessage("Ready")

        if controller is not None:
            self.refresh()

    # -- Menu -------------------------------------------------------------- #
    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
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
        self._act_install.setEnabled(False)
        self._act_uninstall.setEnabled(False)

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
        if self.controller is not None and len(names) == 1:
            md = self.controller.pd.mod_item(names[0])
            if md is not None:
                self._show_details(md)

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
