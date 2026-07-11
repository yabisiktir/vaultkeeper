"""InstallationAnalyser — the installation folder browser + health dialog.

VB ``InstallationAnalyser``.

Tabbed:

* **Browser** — an ``NWN Folders`` list (each installed game folder + its file count
  and size) filtering a ``File Name`` / ``Installation Source`` / ``Size`` /
  ``Modified`` table, with the total installed-file size at the foot (VB LvFolders →
  LvFiles + LbTotalSize).
* **Issues** — installation totals plus the flagged files (changed game originals,
  unknown-source installed files).

Built on ``ProfileController.installation_browser_report`` / ``installation_report``.
"""

from __future__ import annotations

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


class InstallationAnalyser(QDialog):
    """A folder browser + issues summary for the installation."""

    def __init__(
        self, browser: dict, report: dict, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Installation Analyser")
        self.setWindowIcon(R.get_icon("InstallationAnalyser_16x"))
        self.resize(720, 500)
        self._browser = browser

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        tabs.addTab(self._build_browser(browser), "Browser")
        tabs.addTab(self._build_issues(report), "Issues")

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("BhInstallationAnalyser", self))
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    # -- Browser tab ------------------------------------------------------ #
    def _build_browser(self, browser: dict) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        panes = QHBoxLayout()
        outer.addLayout(panes, 1)

        self.folders = QListWidget()
        self.folders.setMaximumWidth(220)
        for folder in browser.get("folders", []):
            item = QListWidgetItem(f"{folder['name']}  ({folder['count']})")
            item.setData(256, folder)  # Qt.UserRole
            self.folders.addItem(item)
        self.folders.currentRowChanged.connect(self._on_folder)
        panes.addWidget(self.folders)

        self.files = QTreeWidget()
        self.files.setHeaderLabels(
            ["File Name", "Installation Source", "Size", "Modified"]
        )
        self.files.setRootIsDecorated(False)
        self.files.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        panes.addWidget(self.files, 1)

        self.total = QLabel(f"Total installed size: {browser.get('total_size', '0 B')}")
        outer.addWidget(self.total)

        if browser.get("folders"):
            self.folders.setCurrentRow(0)
        return page

    def _on_folder(self, row: int) -> None:
        self.files.clear()
        folders = self._browser.get("folders", [])
        if not (0 <= row < len(folders)):
            return
        for f in folders[row]["files"]:
            self.files.addTopLevelItem(
                QTreeWidgetItem([f["filename"], f["source"], f["size"], f["modified"]])
            )

    # -- Issues tab ------------------------------------------------------- #
    def _build_issues(self, report: dict) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        summary = (
            f"Mods: {report.get('installed_mods', 0):,} installed / "
            f"{report.get('total_mods', 0):,} total     "
            f"Installed files: {report.get('installed_files', 0):,}     "
            f"Original files: {report.get('original_files', 0):,}"
        )
        layout.addWidget(QLabel(summary))
        flags = (
            f"Changed originals: {report.get('changed_originals', 0):,}     "
            f"Unknown-source files: {report.get('unknown_source', 0):,}"
        )
        layout.addWidget(QLabel(flags))

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Category", "File"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for issue in report.get("issues", []):
            self.table.addTopLevelItem(
                QTreeWidgetItem([issue["category"], issue["file"]])
            )
        layout.addWidget(self.table)
        if not report.get("issues"):
            layout.addWidget(QLabel("No issues detected."))
        return page

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> InstallationAnalyser:
        dlg = cls(
            controller.installation_browser_report(),
            controller.installation_report(),
            parent,
        )
        dlg.show()
        return dlg
