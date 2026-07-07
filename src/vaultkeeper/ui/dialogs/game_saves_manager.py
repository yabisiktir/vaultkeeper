"""GameSavesManager — the game-saves listing dialog (VB ``GameManager``).

Lists the current NWN game saves (folder, save name, in-module location, save type,
size) with a summary line, from ``ProfileController.game_saves_report``. Read-only
first version; the archive / reduce / restore actions come later.
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


class GameSavesManager(QDialog):
    """A read-only table of the current game saves plus totals."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Game Saves Manager")
        self.setWindowIcon(R.get_icon("GameManager16"))
        self.resize(620, 440)

        layout = QVBoxLayout(self)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Folder", "Save Name", "Location", "Type", "Size"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for row in report.get("rows", []):
            self.table.addTopLevelItem(
                QTreeWidgetItem(
                    [row["name"], row["save"], row["location"], row["type"], row["size"]]
                )
            )
        layout.addWidget(self.table)

        count = report.get("count", 0)
        current = report.get("current") or "—"
        total = report.get("total_size") or "0 B"
        layout.addWidget(
            QLabel(f"Saves: {count:,}    Current game: {current}    Total size: {total}")
        )

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> GameSavesManager:
        """Build and show the manager for a controller's game-saves report."""
        dlg = cls(controller.game_saves_report(), parent)
        dlg.show()
        return dlg
