"""PlayDataViewPending — play sessions awaiting attribution (VB ``PlayDataViewPending``).

When the play loop records a completed game whose mod GameMapper could not confirm,
the session is held as *pending*. This dialog lists those pending records
(mod / completed / time played / user) so the user can review them. Built on
``ProfileController.pending_play_report``. Read-only.
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

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R


class PlayDataViewPending(QDialog):
    """A read-only table of pending (unattributed) play-time records."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pending Play Data")
        self.setWindowIcon(R.get_icon("Time_Green_16x"))
        geometry.remember(self, "PlayDataViewPending", 560, 380)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Play sessions recorded but not yet attributed to a mod:")
        )

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Mod", "Completed", "Time Played", "User"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row in report.get("rows", []):
            self.table.addTopLevelItem(
                QTreeWidgetItem(
                    [row["mod"], row["completed"], row["play_time"], row["user"]]
                )
            )
        layout.addWidget(self.table, 1)

        self.summary = QLabel(f"Pending records: {report.get('count', 0):,}")
        layout.addWidget(self.summary)
        if not report.get("rows"):
            layout.addWidget(QLabel("No pending play data."))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> PlayDataViewPending:
        """Build and show the pending-play-data view for a controller."""
        dlg = cls(controller.pending_play_report(), parent)
        dlg.show()
        return dlg
