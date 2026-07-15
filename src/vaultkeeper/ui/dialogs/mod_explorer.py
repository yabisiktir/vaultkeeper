"""ModExplorer — the all-mods table dialog (VB ``ModExplorer``).

A sortable table of every mod with its group, state, rating, file count, play time
and completed count, from ``ProfileController.mod_explorer_report``, with a filter
bar (name search / state / only-completed) — a bounded port of the VB filter
subsystem (text + state + rating + group + prefix filters).
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
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R

_HEADERS = ["Mod", "Group", "State", "Rating", "Files", "Time Played", "Completed"]


class ModExplorer(QDialog):
    """A sortable, read-only table of all mods with a filter bar."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mod Explorer")
        self.setWindowIcon(R.get_icon("Mod Explorer 1"))
        self.resize(760, 500)
        self._rows = list(report.get("rows", []))

        layout = QVBoxLayout(self)

        # Filter bar (VB filter toolbar — bounded: name / state / only-completed).
        bar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by mod or group name…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._populate)
        bar.addWidget(self._search, 1)
        bar.addWidget(QLabel("State:"))
        self._state = QComboBox()
        self._state.addItem("All states", "")
        for state in sorted({r["state"] for r in self._rows if r["state"]}):
            self._state.addItem(state, state)
        self._state.currentIndexChanged.connect(self._populate)
        bar.addWidget(self._state)
        self._only_completed = QCheckBox("Completed only")
        self._only_completed.stateChanged.connect(self._populate)
        bar.addWidget(self._only_completed)
        layout.addLayout(bar)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(_HEADERS)
        self.table.setRootIsDecorated(False)
        self.table.setSortingEnabled(True)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self._count_label = QLabel()
        layout.addWidget(self._count_label)
        self._populate()

    def _passes(self, row: dict) -> bool:
        query = self._search.text().strip().lower()
        if query and query not in row["mod"].lower() and query not in row["group"].lower():
            return False
        want_state = self._state.currentData()
        if want_state and row["state"] != want_state:
            return False
        return not (self._only_completed.isChecked() and not row["completed"])

    def _populate(self, *_args) -> None:
        self.table.setSortingEnabled(False)
        self.table.clear()
        shown = 0
        for row in self._rows:
            if not self._passes(row):
                continue
            shown += 1
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
            item.setData(4, Qt.ItemDataRole.UserRole, row["files"])
            item.setData(6, Qt.ItemDataRole.UserRole, row["completed"])
            self.table.addTopLevelItem(item)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        total = len(self._rows)
        self._count_label.setText(
            f"{shown:,} of {total:,} mod(s)." if shown != total else f"{total:,} mod(s)."
        )

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> ModExplorer:
        dlg = cls(controller.mod_explorer_report(), parent)
        dlg.show()
        return dlg
