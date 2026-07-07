"""ModExplorer — the all-mods table dialog (VB ``ModExplorer``).

A sortable table of every mod with its group, state, rating, file count, play time
and completed count, from ``ProfileController.mod_explorer_report``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R

_HEADERS = ["Mod", "Group", "State", "Rating", "Files", "Time Played", "Completed"]


class ModExplorer(QDialog):
    """A sortable, read-only table of all mods."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mod Explorer")
        self.setWindowIcon(R.get_icon("Mod Explorer 1"))
        self.resize(760, 500)

        layout = QVBoxLayout(self)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(_HEADERS)
        self.table.setRootIsDecorated(False)
        self.table.setSortingEnabled(True)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row in report.get("rows", []):
            item = QTreeWidgetItem(
                [
                    row["mod"],
                    row["group"],
                    row["state"],
                    row["rating"],
                    f"{row['files']:,}",
                    row["played"],
                    f"{row['completed']:,}" if row["completed"] else "",
                ]
            )
            # Numeric columns sort by value, not string.
            item.setData(4, Qt.ItemDataRole.UserRole, row["files"])
            item.setData(6, Qt.ItemDataRole.UserRole, row["completed"])
            self.table.addTopLevelItem(item)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        layout.addWidget(self.table)

        layout.addWidget(QLabel(f"{report.get('count', 0):,} mod(s)."))

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> ModExplorer:
        dlg = cls(controller.mod_explorer_report(), parent)
        dlg.show()
        return dlg
