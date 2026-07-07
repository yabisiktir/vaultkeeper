"""DependencyManager — the mod dependency dialog (VB ``DependencyManager``).

Lists each mod's declared dependencies and the mods that require it, from
``ProfileController.dependencies_report`` (the ProfileData dependency graph).
"""

from __future__ import annotations

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


class DependencyManager(QDialog):
    """A read-only table of mod dependencies."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dependency Manager")
        self.setWindowIcon(R.get_icon("DependencyGraph_16x"))
        self.resize(640, 440)

        layout = QVBoxLayout(self)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Mod", "Depends On", "Required By"])
        self.table.setRootIsDecorated(False)
        header = self.table.header()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for row in report.get("rows", []):
            self.table.addTopLevelItem(
                QTreeWidgetItem(
                    [
                        row["mod"],
                        ", ".join(row["depends_on"]),
                        ", ".join(row["required_by"]),
                    ]
                )
            )
        layout.addWidget(self.table)

        count = report.get("count", 0)
        layout.addWidget(
            QLabel(f"{count:,} mod(s) with dependencies." if count else "No dependencies.")
        )

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> DependencyManager:
        dlg = cls(controller.dependencies_report(), parent)
        dlg.show()
        return dlg
