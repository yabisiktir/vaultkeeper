"""InstallationAnalyser — the installation health dialog (VB ``InstallationAnalyser``).

Shows installation totals plus the flagged files (changed game originals, unknown-
source installed files), from ``ProfileController.installation_report``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button


class InstallationAnalyser(QDialog):
    """A read-only summary + issues table for the installation."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Installation Analyser")
        self.setWindowIcon(R.get_icon("InstallationAnalyser_16x"))
        self.resize(620, 460)

        layout = QVBoxLayout(self)

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

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("BhInstallationAnalyser", self))
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> InstallationAnalyser:
        dlg = cls(controller.installation_report(), parent)
        dlg.show()
        return dlg
