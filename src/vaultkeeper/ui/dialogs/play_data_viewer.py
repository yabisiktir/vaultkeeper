"""PlayDataViewer — the play-time report dialog (VB ``PlayDataViewer``).

Shows per-mod play times (longest first) and the NWN totals, from
``ProfileController.play_times_report``.

Almost read-only. The one thing it writes is a game's **start date**, because
play tracking only begins when you launch through Vaultkeeper: a campaign begun
before that has hours against it and no start, and there is nowhere else to say
when it began. Right-click a row (VB ``EditStartTime``).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button


class PlayDataViewer(QDialog):
    """A read-only table of per-mod play times plus totals."""

    def __init__(
        self,
        report: dict,
        parent: QWidget | None = None,
        *,
        daily: dict | None = None,
        controller=None,
        show_report: bool = False,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Mods Played")
        self.setWindowIcon(R.get_icon("PlayTime_16x"))
        geometry.remember(self, "PlayDataViewer", 520, 420)

        layout = QVBoxLayout(self)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Mod", "Time Played", "Started"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Right-click a game to say when it was started (VB EditStartTime). Only
        # offered when there is a controller to write through.
        if controller is not None:
            self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.table.customContextMenuRequested.connect(self._on_row_menu)
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

        # Average hours per day (VB DailyPlayTimeInfo / GetDailyPlayInfo).
        if daily and daily.get("recorded"):
            layout.addWidget(QLabel(f"Average per day: {daily['average_label']}"))

        # The per-day report (VB PlayDataViewer.ShowReport, reached with
        # Ctrl+click on the menu bar's play-time readout).
        self.report = QTreeWidget()
        self.report.setHeaderLabels(["Day", "Played"])
        self.report.setRootIsDecorated(False)
        self.report.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for day in (daily or {}).get("days", []):
            self.report.addTopLevelItem(QTreeWidgetItem([day["date"], day["label"]]))
        self.report.setVisible(show_report)
        layout.addWidget(self.report)

        self.report_button = QPushButton(
            "Hide Daily Report" if show_report else "Daily Report"
        )
        self.report_button.setToolTip("How long you played on each recorded day.")
        self.report_button.clicked.connect(self._toggle_report)

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("BhModsPlayed", self))
        buttons.addWidget(self.report_button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _toggle_report(self) -> None:
        showing = not self.report.isVisible()
        self.report.setVisible(showing)
        self.report_button.setText("Hide Daily Report" if showing else "Daily Report")

    # -- Setting a game's start date (VB EditStartTime) --------------------- #
    def _on_row_menu(self, point) -> None:
        item = self.table.itemAt(point)
        if item is None:
            return
        menu = QMenu(self)
        existing = self._controller.play_start_date(item.text(0))
        menu.addAction(
            "Change Start Date…" if existing else "Specify Start Date…",
            lambda: self._edit_start_date(item),
        )
        menu.exec(self.table.viewport().mapToGlobal(point))

    def _edit_start_date(self, item: QTreeWidgetItem) -> None:
        """Ask for the date and record it.

        VB's wording is worth keeping: the Game Saves Manager is where people
        find the answer, by looking at their earliest save's creation date.
        """
        from datetime import datetime

        mod = item.text(0)
        existing = self._controller.play_start_date(mod)
        default = (existing or datetime.now()).strftime(_DATE_FORMAT)
        text, ok = QInputDialog.getText(
            self,
            f"{mod}'s start date and time",
            "Specify the start date as dd MMM yy, hh:mm:ss am/pm\n"
            "(eg 05 Jan 24, 05:04:31 pm).\n\n"
            "The Game Saves Manager can find it for you: look at the Date "
            "Created of your earliest save for this game.",
            text=default,
        )
        if not ok or not text.strip():
            return
        started = _parse_started(text.strip())
        if started is None:
            QMessageBox.warning(
                self,
                "Start Date",
                f"“{text.strip()}” is not a date in the form {default}.",
            )
            return
        result = self._controller.set_play_start_date(mod, started)
        if not result["ok"]:
            QMessageBox.warning(self, "Start Date", result["message"])
            return
        item.setText(2, started.strftime(_DATE_FORMAT))

    @classmethod
    def show_for(
        cls, controller, parent: QWidget | None = None, *, show_report: bool = False
    ) -> PlayDataViewer:
        """Build and show the viewer for a controller's play report."""
        dlg = cls(
            controller.play_times_report(),
            parent,
            daily=controller.daily_play_report(),
            controller=controller,
            show_report=show_report,
        )
        dlg.show()
        return dlg


#: How a start date is written and read back (VB ``StartDateFormat(0)``).
_DATE_FORMAT = "%d %b %y, %I:%M:%S %p"


def _parse_started(text: str):
    """A typed start date, or ``None``. Time of day is optional."""
    from datetime import datetime

    for fmt in (_DATE_FORMAT, "%d %b %y", "%d %b %Y, %I:%M:%S %p", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None
