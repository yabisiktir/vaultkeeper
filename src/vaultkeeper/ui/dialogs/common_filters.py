"""CommonFiltersDialog — shared Group + Rating include/exclude filter.

Faithful port of VB ``CommonFiltersDialogue``.

Two checkable lists: which **groups** and which **ratings** to show.  A checked
item is *included*.  Used by the Mod Play Viewer (VB ``ModPlayViewer`` opens this
via its filter toolbar) to narrow the displayed mods by group and by rating —
faithful to the VB multi-select dialog, replacing the port's earlier single-group
combo (which could not exclude by rating or show several groups at once).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _checkable_list(values: list[str], included: dict[str, bool]) -> QListWidget:
    lst = QListWidget()
    for value in values:
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        state = included.get(value, True)
        item.setCheckState(Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)
        lst.addItem(item)
    return lst


class CommonFiltersDialog(QDialog):
    """Include/exclude by Group and Rating (VB CommonFiltersDialogue)."""

    def __init__(
        self,
        groups: list[str],
        ratings: list[str],
        group_included: dict[str, bool],
        rating_included: dict[str, bool],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filters")
        self.resize(420, 380)

        layout = QVBoxLayout(self)
        lists = QHBoxLayout()

        group_col = QVBoxLayout()
        group_col.addWidget(QLabel("Groups"))
        self._groups = _checkable_list(groups, group_included)
        group_col.addWidget(self._groups)
        lists.addLayout(group_col)

        rating_col = QVBoxLayout()
        rating_col.addWidget(QLabel("Ratings"))
        self._ratings = _checkable_list(ratings, rating_included)
        rating_col.addWidget(self._ratings)
        lists.addLayout(rating_col)
        layout.addLayout(lists)

        bar = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        clear_all = QPushButton("Clear All")
        clear_all.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        bar.addWidget(select_all)
        bar.addWidget(clear_all)
        bar.addStretch(1)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bar.addWidget(apply_btn)
        bar.addWidget(cancel)
        layout.addLayout(bar)

    def _set_all(self, state: Qt.CheckState) -> None:
        for lst in (self._groups, self._ratings):
            for i in range(lst.count()):
                lst.item(i).setCheckState(state)

    @staticmethod
    def _collect(lst: QListWidget) -> dict[str, bool]:
        return {
            lst.item(i).text(): lst.item(i).checkState() == Qt.CheckState.Checked
            for i in range(lst.count())
        }

    def group_filters(self) -> dict[str, bool]:
        return self._collect(self._groups)

    def rating_filters(self) -> dict[str, bool]:
        return self._collect(self._ratings)
