"""ModExplorer — the all-mods table dialog (VB ``ModExplorer``).

A sortable table of every mod with its group, state, rating, file count, play time
and completed count, from ``ProfileController.mod_explorer_report``, with a filter
bar (name search / state / only-completed) — a bounded port of the VB filter
subsystem (text + state + rating + group + prefix filters).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button

_HEADERS = ["Mod", "Group", "State", "Rating", "Files", "Time Played", "Completed"]


class ModExplorer(QDialog):
    """A sortable, read-only table of all mods with a filter bar."""

    def __init__(
        self, report: dict, on_select=None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mod Explorer")
        self.setWindowIcon(R.get_icon("Mod Explorer 1"))
        self.resize(760, 500)
        self._rows = list(report.get("rows", []))
        self._on_select = on_select

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

        # Bottom bar: help (VB TsHelpExplorer) + Copy Names + Select + Close.
        buttons = QHBoxLayout()
        buttons.addWidget(help_button("TsHelpExplorer", self))
        buttons.addStretch(1)
        copy_names = QPushButton("Copy Names")
        copy_names.clicked.connect(self._on_copy_names)
        buttons.addWidget(copy_names)
        select = QPushButton("Select")
        select.clicked.connect(self._on_select_mod)
        buttons.addWidget(select)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

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

    def _on_copy_names(self) -> None:
        """Copy selected mod names to clipboard, one per line."""
        names = []
        for i in range(self.table.topLevelItemCount()):
            item = self.table.topLevelItem(i)
            if item and item.isSelected():
                names.append(item.text(0))
        if names:
            QApplication.clipboard().setText("\n".join(names))

    def _on_select_mod(self) -> None:
        """Jump to the selected mod in the main window and close."""
        if not self._on_select:
            return
        current = self.table.currentItem()
        if current:
            self._on_select(current.text(0))
            self.accept()

    @classmethod
    def show_for(
        cls, controller, on_select=None, parent: QWidget | None = None
    ) -> ModExplorer:
        dlg = cls(controller.mod_explorer_report(), on_select, parent)
        dlg.show()
        return dlg
