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
        *,
        prefixes: list[dict] | None = None,
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

        # Name prefixes (VB LvPrefixFilters). A prefix is only matched text —
        # unticking one hides every mod whose *name starts with it*. There is no
        # prefix field on a mod, in VB either, so this list is the whole feature.
        prefix_col = QVBoxLayout()
        prefix_col.addWidget(QLabel("Name prefixes"))
        self._prefixes = QListWidget()
        for entry in prefixes or []:
            self._add_prefix_row(entry.get("prefix", ""), entry.get("included", True))
        self._prefixes.setToolTip(
            "Untick a prefix to hide every mod whose name starts with it."
        )
        prefix_col.addWidget(self._prefixes)
        prefix_buttons = QHBoxLayout()
        for label, slot in (
            ("Add…", self._on_add_prefix),
            ("Edit…", self._on_edit_prefix),
            ("Remove", self._on_remove_prefix),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            prefix_buttons.addWidget(btn)
        prefix_col.addLayout(prefix_buttons)
        lists.addLayout(prefix_col)
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

    # -- Prefixes (VB TsAddPrefix / TsEditPrefix / TsRemovePrefix) ---------- #
    #: Punctuation a prefix is often made of, named so the row is readable
    #: (VB ``CharDescriptions``).
    _CHAR_NAMES = {
        ".": "Period", ",": "Comma", "'": "Single Quote",
        "-": "Hyphen", "_": "Underscore", "~": "Tilde",
    }

    def _add_prefix_row(self, prefix: str, included: bool) -> None:
        label = prefix
        if prefix in self._CHAR_NAMES:
            label = f"{prefix} ({self._CHAR_NAMES[prefix]})"
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, prefix)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(
            Qt.CheckState.Checked if included else Qt.CheckState.Unchecked
        )
        self._prefixes.addItem(item)

    def _ask_prefix(self, title: str, initial: str = "") -> str:
        from PySide6.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(self, title, "Name prefix:", text=initial)
        return text.strip() if ok else ""

    def _on_add_prefix(self) -> None:
        prefix = self._ask_prefix("Add Prefix")
        if not prefix or prefix in self.prefix_values():
            return
        self._add_prefix_row(prefix, True)

    def _on_edit_prefix(self) -> None:
        item = self._prefixes.currentItem()
        if item is None:
            return
        current = item.data(Qt.ItemDataRole.UserRole)
        prefix = self._ask_prefix("Edit Prefix", current)
        if not prefix or prefix == current:
            return
        checked = item.checkState()
        row = self._prefixes.row(item)
        self._prefixes.takeItem(row)
        self._add_prefix_row(prefix, checked == Qt.CheckState.Checked)

    def _on_remove_prefix(self) -> None:
        item = self._prefixes.currentItem()
        if item is not None:
            self._prefixes.takeItem(self._prefixes.row(item))

    def prefix_values(self) -> list[str]:
        return [
            self._prefixes.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._prefixes.count())
        ]

    def prefix_filters(self) -> list[dict]:
        """``[{"prefix", "included"}]`` for persisting (VB ``SavePrefixFilters``)."""
        return [
            {
                "prefix": self._prefixes.item(i).data(Qt.ItemDataRole.UserRole),
                "included": self._prefixes.item(i).checkState() == Qt.CheckState.Checked,
            }
            for i in range(self._prefixes.count())
        ]

    def _set_all(self, state: Qt.CheckState) -> None:
        for lst in (self._groups, self._ratings, self._prefixes):
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
