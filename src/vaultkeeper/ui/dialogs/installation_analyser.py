"""InstallationAnalyser — the installation folder browser + health dialog.

VB ``InstallationAnalyser``.

Tabbed:

* **Browser** — an ``NWN Folders`` list (each installed game folder + its file count
  and size) filtering a ``File Name`` / ``Installation Source`` / ``Size`` /
  ``Modified`` table, with the total installed-file size at the foot (VB LvFolders →
  LvFiles + LbTotalSize).
* **Issues** — installation totals plus the flagged files (changed game originals,
  unknown-source installed files).

**Refresh** re-runs the analysis (VB BtRefresh); **Select** jumps the main window to
the highlighted file's installing mod (VB BtSelect). Built on
``ProfileController.installation_browser_report`` / ``installation_report``.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button

_FILE_ROLE = Qt.ItemDataRole.UserRole + 1
_SOURCE_ROLE = Qt.ItemDataRole.UserRole


class InstallationAnalyser(QDialog):
    """A folder browser + issues summary for the installation."""

    def __init__(
        self,
        controller,
        on_select: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._on_select = on_select
        self.setWindowTitle("Installation Analyser")
        self.setWindowIcon(R.get_icon("InstallationAnalyser_16x"))
        geometry.remember(self, "InstallationAnalyser", 720, 500)
        self._browser: dict = {}
        self._report: dict = {}

        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)
        self._tabs.addTab(self._build_browser(), "Browser")
        self._tabs.addTab(self._build_issues(), "Issues")

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("BhInstallationAnalyser", self))
        self._refresh_button = QPushButton("Refresh")
        self._refresh_button.setToolTip("Re-run the installation analysis")
        self._refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(self._refresh_button)
        self._select_button = QPushButton("Select")
        self._select_button.setToolTip("Select the highlighted file's mod in the main window")
        self._select_button.clicked.connect(self._on_select_mod)
        buttons.addWidget(self._select_button)
        # newtopic59.htm: "The Installation Analyser displays a Convert button
        # when a NWM file is selected." An .nwm cannot be opened in the Toolset;
        # Convert makes a .mod copy that can.
        self._convert_button = QPushButton("Convert")
        self._convert_button.setToolTip(
            "Convert the selected .nwm module to a .mod the Toolset can open"
        )
        self._convert_button.clicked.connect(self._on_convert_nwm)
        self._convert_button.setVisible(False)
        buttons.addWidget(self._convert_button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.refresh()

    # -- data ------------------------------------------------------------- #
    def refresh(self) -> None:
        """Re-run the analysis and repopulate both tabs (VB BtRefresh)."""
        if self._controller is not None:
            self._browser = self._controller.installation_browser_report()
            self._report = self._controller.installation_report()
        self._populate_browser()
        self._populate_issues()

    # -- Browser tab ------------------------------------------------------ #
    def _build_browser(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        panes = QHBoxLayout()
        outer.addLayout(panes, 1)

        self.folders = QListWidget()
        self.folders.setMaximumWidth(220)
        self.folders.currentRowChanged.connect(self._on_folder)
        # Double-click does the row's own action, as in the original: a folder
        # opens (VB LvFolders → CmOpenFolder), a file shows its properties
        # (LvFiles → ShowProperties). Both were right-click-only here.
        self.folders.itemDoubleClicked.connect(lambda *_: self._on_open_folder())
        panes.addWidget(self.folders)

        self.files = QTreeWidget()
        self.files.setHeaderLabels(["File Name", "Installation Source", "Size", "Modified"])
        self.files.setRootIsDecorated(False)
        self.files.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._on_files_menu)
        self.files.itemDoubleClicked.connect(lambda *_: self._on_file_properties())
        self.files.currentItemChanged.connect(lambda *_: self._sync_convert())
        panes.addWidget(self.files, 1)

        self.total = QLabel()
        outer.addWidget(self.total)
        return page

    def _populate_browser(self) -> None:
        self.folders.blockSignals(True)
        self.folders.clear()
        for folder in self._browser.get("folders", []):
            item = QListWidgetItem(f"{folder['name']}  ({folder['count']})")
            item.setData(_SOURCE_ROLE, folder)
            self.folders.addItem(item)
        self.folders.blockSignals(False)
        self.total.setText(
            f"Total installed size: {self._browser.get('total_size', '0 B')}"
        )
        if self._browser.get("folders"):
            self.folders.setCurrentRow(0)
        else:
            self.files.clear()

    def _on_folder(self, row: int) -> None:
        self.files.clear()
        folders = self._browser.get("folders", [])
        if not (0 <= row < len(folders)):
            return
        for f in folders[row]["files"]:
            item = QTreeWidgetItem([f["filename"], f["source"], f["size"], f["modified"]])
            item.setData(0, _SOURCE_ROLE, f["source"])
            # The row only. Attaching the *folder* here — as this briefly did —
            # hands PySide6 a dict holding every file in it, once per row, and
            # it converts the whole structure each time: 40 seconds for the
            # owner's 6,392-file override folder, against 0.13 for the row alone.
            item.setData(0, _FILE_ROLE, f)
            self.files.addTopLevelItem(item)

    def _on_files_menu(self, point) -> None:
        """Open Folder / Properties on a file (VB CmOpenFolder / CmProperties)."""
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu

        item = self.files.currentItem()
        row = item.data(0, _FILE_ROLE) if item is not None else None
        menu = QMenu(self)
        reveal = menu.addAction(R.get_icon("OpenFolder_16x"), "Open Folder")
        reveal.setEnabled(row is not None)
        reveal.triggered.connect(self._on_open_folder)
        props = menu.addAction(R.get_icon("PropertiesW10"), "Properties")
        props.setEnabled(row is not None)
        props.triggered.connect(self._on_file_properties)
        menu.exec(self.files.viewport().mapToGlobal(point) if point else QCursor.pos())

    def _current_file_path(self):
        from pathlib import Path as _Path

        item = self.files.currentItem()
        row = item.data(0, _FILE_ROLE) if item is not None else None
        if not row:
            return None
        path = row.get("path") or row.get("full_path")
        return _Path(path) if path else None

    def _on_open_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        path = self._current_file_path()
        folder = path.parent if path is not None else None
        if folder is not None and folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_file_properties(self) -> None:
        """The facts VB's shell dialog would show, plus where the file came from."""
        from PySide6.QtWidgets import QMessageBox

        item = self.files.currentItem()
        row = item.data(0, _FILE_ROLE) if item is not None else None
        if not row:
            return
        path = self._current_file_path()
        lines = [
            f"File: {row.get('filename', '')}",
            f"Installed by: {row.get('source') or 'no mod in this profile'}",
            f"Size: {row.get('size', '')}",
            f"Modified: {row.get('modified', '')}",
        ]
        if path is not None:
            lines.append(f"Path: {path}")
        box = QMessageBox(self)
        box.setWindowTitle("File Properties")
        box.setText(row.get("filename", "File"))
        box.setInformativeText("\n".join(lines))
        box.exec()

    def _on_select_mod(self) -> None:
        item = self.files.currentItem()
        if item is None or self._on_select is None:
            return
        source = item.data(0, _SOURCE_ROLE)
        if source:
            self._on_select(source)
            self.accept()

    def _selected_nwm_path(self):
        """The selected file's path if it is an ``.nwm``, else ``None``."""
        path = self._current_file_path()
        if path is not None and path.suffix.lower() == ".nwm":
            return path
        return None

    def _sync_convert(self) -> None:
        """Show Convert only for a selected .nwm (newtopic59.htm)."""
        self._convert_button.setVisible(self._selected_nwm_path() is not None)

    def _on_convert_nwm(self) -> None:
        """Convert the selected .nwm into a Toolset-openable .mod mod."""
        from PySide6.QtWidgets import QMessageBox

        nwm = self._selected_nwm_path()
        if nwm is None or self._controller is None:
            return
        result = self._controller.convert_nwm_to_mod(nwm)
        if not result["ok"]:
            QMessageBox.information(self, "Convert Module", result["message"])
            return
        # VB selects the converted mod in the main window and closes; the topic
        # ends "The converted Mod is selected … ready to be opened with the
        # Toolset."
        QMessageBox.information(self, "Convert Module", result["message"])
        if self._on_select is not None:
            self._on_select(result["mod_name"])
            self.accept()

    # -- Issues tab ------------------------------------------------------- #
    def _build_issues(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._summary = QLabel()
        layout.addWidget(self._summary)
        self._flags = QLabel()
        layout.addWidget(self._flags)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Category", "File"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self._no_issues = QLabel("No issues detected.")
        layout.addWidget(self._no_issues)
        return page

    def _populate_issues(self) -> None:
        r = self._report
        self._summary.setText(
            f"Mods: {r.get('installed_mods', 0):,} installed / "
            f"{r.get('total_mods', 0):,} total     "
            f"Installed files: {r.get('installed_files', 0):,}     "
            f"Original files: {r.get('original_files', 0):,}"
        )
        self._flags.setText(
            f"Changed originals: {r.get('changed_originals', 0):,}     "
            f"Unknown-source files: {r.get('unknown_source', 0):,}"
        )
        self.table.clear()
        issues = r.get("issues", [])
        for issue in issues:
            self.table.addTopLevelItem(QTreeWidgetItem([issue["category"], issue["file"]]))
        self._no_issues.setVisible(not issues)

    @classmethod
    def show_for(
        cls, controller, on_select=None, parent: QWidget | None = None
    ) -> InstallationAnalyser:
        dlg = cls(controller, on_select, parent)
        dlg.show()
        return dlg
