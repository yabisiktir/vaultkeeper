"""A searchable feat picker — choose a feat id to add to a character.

Lists every known feat (base + PRC) with a live text filter. PRC feats are marked
because editing them may not persist in-game (PRC regenerates its own feats).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

_FEAT_ID = Qt.ItemDataRole.UserRole


class FeatPickerDialog(QDialog):
    """Pick a feat from ``[(id, name)]``; ids >= ``base_count`` are marked PRC."""

    def __init__(
        self, feats: list[tuple[int, str]], base_count: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add a Feat")
        self.resize(460, 480)
        layout = QVBoxLayout(self)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Search feats…")
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)

        self._list = QListWidget()
        for feat_id, name in sorted(feats, key=lambda pair: pair[1].lower()):
            suffix = "" if feat_id < base_count else "  — PRC"
            item = QListWidgetItem(f"{name}  [{feat_id}]{suffix}")
            item.setData(_FEAT_ID, feat_id)
            self._list.addItem(item)
        self._list.itemDoubleClicked.connect(lambda _i: self.accept())
        layout.addWidget(self._list, 1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _apply_filter(self, text: str) -> None:
        needle = text.lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(needle not in item.text().lower())

    def selected_feat_id(self) -> int | None:
        item = self._list.currentItem()
        return item.data(_FEAT_ID) if item is not None else None
