"""PlayDataViewer — the play-time report dialog (VB ``PlayDataViewer``).

Shows per-mod play times (longest first) and the NWN totals, from
``ProfileController.play_times_report``. Read-only; a first faithful version of the
VB viewer (the pending-times / completed-date views come later).
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


class PlayDataViewer(QDialog):
    """A read-only table of per-mod play times plus totals."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mods Played")
        self.setWindowIcon(R.get_icon("PlayTime_16x"))
        self.resize(520, 420)

        layout = QVBoxLayout(self)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Mod", "Time Played", "Started"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row in report.get("rows", []):
            self.table.addTopLevelItem(
                QTreeWidgetItem([row["mod"], row["time"], row["started"]])
            )
        layout.addWidget(self.table)

        total = report.get("total_played") or "NWN not played"
        most = report.get("most_in_one_day") or "—"
        last = report.get("last_played") or "—"
        summary = QLabel(
            f"Total played: {total}    Most in one day: {most}    Last played: {last}"
        )
        layout.addWidget(summary)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> PlayDataViewer:
        """Build and show the viewer for a controller's play report."""
        dlg = cls(controller.play_times_report(), parent)
        dlg.show()
        return dlg
