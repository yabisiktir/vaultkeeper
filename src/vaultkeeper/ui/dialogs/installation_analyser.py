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

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button

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
        self.resize(720, 500)
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
        panes.addWidget(self.folders)

        self.files = QTreeWidget()
        self.files.setHeaderLabels(["File Name", "Installation Source", "Size", "Modified"])
        self.files.setRootIsDecorated(False)
        self.files.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
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
            self.files.addTopLevelItem(item)

    def _on_select_mod(self) -> None:
        item = self.files.currentItem()
        if item is None or self._on_select is None:
            return
        source = item.data(0, _SOURCE_ROLE)
        if source:
            self._on_select(source)
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
