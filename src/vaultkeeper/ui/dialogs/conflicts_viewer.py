"""ConflictsViewer — the mod-file conflicts dialog (VB ``FileConflictsViewer``).

Lists every installed game file that more than one mod's installer maps onto, the mod
that currently owns it (the engine's last-by-comparer winner) and the full set of
claimants, from ``ProfileController.conflicts_report``.
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


class ConflictsViewer(QDialog):
    """A read-only table of file conflicts and their winning mod."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mod File Conflicts")
        self.setWindowIcon(R.get_icon("Overridden"))
        self.resize(640, 440)

        layout = QVBoxLayout(self)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["File", "Winner", "Conflicting Mods"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for row in report.get("rows", []):
            others = ", ".join(m for m in row["mods"] if m != row["winner"])
            self.table.addTopLevelItem(
                QTreeWidgetItem([row["file"], row["winner"], others])
            )
        layout.addWidget(self.table)

        count = report.get("count", 0)
        if count:
            layout.addWidget(QLabel(f"{count:,} file(s) with conflicts."))
        else:
            layout.addWidget(QLabel("No file conflicts."))

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("ManageModFileConflicts", self))
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> ConflictsViewer:
        """Build and show the viewer for a controller's conflicts report."""
        dlg = cls(controller.conflicts_report(), parent)
        dlg.show()
        return dlg
