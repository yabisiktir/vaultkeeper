"""ModPlayViewer — mods sorted by date completed (VB ``ModPlayViewer``).

A tabular view of every mod that has a module file, ordered from the oldest last
date completed. Selecting a mod reveals its group, best weapon, web link, notes
and per-user play-time history. Built on ``ProfileController.mod_play_report``.

Carries the VB *filter options* toolbar (Group + Only-completed) that filter the
displayed list. The rating/end-level filters and the Select/Recent actions that drive
the main window are deferred.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.state import State
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button
from vaultkeeper.ui.file_view import icon_name_for_state

_ROW_ROLE = Qt.ItemDataRole.UserRole
_ALL_GROUPS = "All Groups"


class ModPlayViewer(QDialog):
    """A read-only table of mods ordered by last date completed."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mods Sorted by Date Completed")
        self.setWindowIcon(R.get_icon("Time_Green_16x"))
        self.resize(760, 560)

        self._rows = report.get("rows", [])

        layout = QVBoxLayout(self)
        # VB heading (ModPlayViewer.Designer LbHeading).
        heading = QLabel(
            "List of Mods sorted by the last date the Mod was completed and ordered "
            "from the oldest to the most recent. You may find this list useful when "
            "choosing which Mod you want to replay."
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)

        # -- Filter options (VB group / only-completed toolbar) ------------- #
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Group:"))
        self.group_filter = QComboBox()
        self.group_filter.addItem(_ALL_GROUPS)
        for group in sorted({r["group"] for r in self._rows if r.get("group")}):
            self.group_filter.addItem(group)
        self.group_filter.currentIndexChanged.connect(self._populate_mods)
        filters.addWidget(self.group_filter)
        self.only_completed = QCheckBox("Only completed")
        self.only_completed.stateChanged.connect(self._populate_mods)
        filters.addWidget(self.only_completed)
        filters.addStretch(1)
        layout.addLayout(filters)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        # -- Mod list (top) ------------------------------------------------- #
        self.mods = QTreeWidget()
        self.mods.setHeaderLabels(
            ["Mod Name", "Completed", "Time Played", "Rating", "Start", "End"]
        )
        self.mods.setRootIsDecorated(False)
        self.mods.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.mods.currentItemChanged.connect(self._on_selection)
        splitter.addWidget(self.mods)

        # -- Detail (bottom) ------------------------------------------------ #
        detail = QWidget()
        dlayout = QVBoxLayout(detail)
        dlayout.setContentsMargins(0, 0, 0, 0)
        self.group_label = QLabel()
        self.weapon_label = QLabel()
        self.link_label = QLabel()
        self.link_label.setOpenExternalLinks(True)
        self.played_label = QLabel()
        self.played_label.setWordWrap(True)
        for w in (self.group_label, self.weapon_label, self.link_label, self.played_label):
            dlayout.addWidget(w)

        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setAlignment(Qt.AlignmentFlag.AlignTop)
        dlayout.addWidget(self.notes, 1)

        self.times = QTreeWidget()
        self.times.setHeaderLabels(["Completed", "Time Played", "User"])
        self.times.setRootIsDecorated(False)
        dlayout.addWidget(self.times, 1)
        splitter.addWidget(detail)
        splitter.setSizes([340, 220])

        # -- Summary -------------------------------------------------------- #
        self._summary_prefix = report.get("summary", "0/0")
        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("BhModsPlayed", self))
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._populate_mods()

    def _populate_mods(self, *_args) -> None:
        """Fill the mod list, applying the group / only-completed filters."""
        group = self.group_filter.currentText()
        only_completed = self.only_completed.isChecked()
        self.mods.clear()
        shown = 0
        for row in self._rows:
            if group != _ALL_GROUPS and row.get("group") != group:
                continue
            if only_completed and not row.get("completed"):
                continue
            item = QTreeWidgetItem(
                [
                    row["mod"],
                    row["completed"],
                    row["play_time"],
                    row["rating"],
                    row["start"],
                    row["end"],
                ]
            )
            item.setIcon(0, R.get_icon(icon_name_for_state(State(row["state"]))))
            item.setToolTip(0, row["played_info"])
            item.setData(0, _ROW_ROLE, row)
            self.mods.addTopLevelItem(item)
            shown += 1
        self.summary.setText(
            f"Shown: {shown:,}    Mods (installed/total): {self._summary_prefix}"
        )
        if shown:
            self.mods.setCurrentItem(self.mods.topLevelItem(0))

    def _on_selection(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        if current is None:
            return
        row = current.data(0, _ROW_ROLE)
        if row is None:
            return
        self.group_label.setText(f"Group: {row['group']}")
        self.weapon_label.setText(f"Best Weapon: {row['best_weapon']}")
        if row["web_link"]:
            self.link_label.setText(
                f'<a href="{row["web_link"]}">{row["web_link"]}</a>'
            )
        else:
            self.link_label.setText("")
        self.played_label.setText(row["played_info"] or "No Play Time history recorded.")
        self.notes.setText(row["notes"])

        self.times.clear()
        for pt in row.get("play_times", []):
            self.times.addTopLevelItem(
                QTreeWidgetItem([pt["completed"], pt["play_time"], pt["user"]])
            )

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> ModPlayViewer:
        """Build and show the viewer for a controller's mod-play report."""
        dlg = cls(controller.mod_play_report(), parent)
        dlg.show()
        return dlg
