"""Customise the Quick Access Toolbar (VB ``MsCustomise`` / the Toolbar Editor).

Two lists and an **Add >>** between them, as in the original: every command the
menus offer on the left, the toolbar as it stands on the right, and the caption
of the selected toolbar entry editable underneath — "You can shorten the text
that will be displayed under the icon and then click Save".

Only commands that already have an icon in the menus can be added, because a
toolbar button with no icon is a blank square: the toolbar shows icons, and may
be set to show them with no caption at all.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.quick_toolbar import QUICK_ITEMS, SEP, ToolItem

_ITEM_ROLE = Qt.ItemDataRole.UserRole


class ToolbarEditor(QDialog):
    """Pick what the quick toolbar carries, and what each button is called."""

    def __init__(self, items, available, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Customise Toolbar")
        self.setWindowIcon(R.get_icon("SettingsCog16"))
        geometry.remember(self, "ToolbarEditor", 680, 460)

        layout = QVBoxLayout(self)
        note = QLabel(
            "Choose a menu command on the left and where it should go on the "
            "right, then click Add. Select a toolbar entry to shorten the text "
            "shown under its icon."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        lists = QHBoxLayout()
        self.available = QListWidget()
        for item in available:
            entry = QListWidgetItem(R.get_icon(item.image), item.caption)
            entry.setData(_ITEM_ROLE, item)
            self.available.addItem(entry)
        lists.addWidget(_titled("Menu Commands", self.available), 1)

        middle = QVBoxLayout()
        middle.addStretch(1)
        self.add_button = QPushButton("Add >>")
        self.add_button.clicked.connect(self._on_add)
        middle.addWidget(self.add_button)
        self.separator_button = QPushButton("Add separator")
        self.separator_button.clicked.connect(lambda: self._insert(SEP))
        middle.addWidget(self.separator_button)
        self.remove_button = QPushButton("<< Remove")
        self.remove_button.clicked.connect(self._on_remove)
        middle.addWidget(self.remove_button)
        self.up_button = QPushButton("Move up")
        self.up_button.clicked.connect(lambda: self._move(-1))
        middle.addWidget(self.up_button)
        self.down_button = QPushButton("Move down")
        self.down_button.clicked.connect(lambda: self._move(1))
        middle.addWidget(self.down_button)
        middle.addStretch(1)
        lists.addLayout(middle)

        self.current = QListWidget()
        self.current.currentItemChanged.connect(lambda *_a: self._sync())
        for item in items:
            self.current.addItem(_row(item))
        lists.addWidget(_titled("Toolbar Commands", self.current), 1)
        layout.addLayout(lists)

        caption_row = QHBoxLayout()
        caption_row.addWidget(QLabel("Text under the icon:"))
        self.caption = QLineEdit()
        self.caption.textEdited.connect(self._on_caption_edited)
        caption_row.addWidget(self.caption, 1)
        layout.addLayout(caption_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._on_restore
        )
        layout.addWidget(buttons)
        self._sync()

    # -- Editing ----------------------------------------------------------- #
    def items(self) -> tuple[ToolItem, ...]:
        """The toolbar as edited."""
        return tuple(
            self.current.item(i).data(_ITEM_ROLE) for i in range(self.current.count())
        )

    def _insert(self, item: ToolItem) -> None:
        row = self.current.currentRow()
        at = row + 1 if row >= 0 else self.current.count()
        self.current.insertItem(at, _row(item))
        self.current.setCurrentRow(at)

    def _on_add(self) -> None:
        chosen = self.available.currentItem()
        if chosen is not None:
            self._insert(chosen.data(_ITEM_ROLE))

    def _on_remove(self) -> None:
        row = self.current.currentRow()
        if row >= 0:
            self.current.takeItem(row)
            self._sync()

    def _move(self, delta: int) -> None:
        row = self.current.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.current.count():
            return
        item = self.current.takeItem(row)
        self.current.insertItem(target, item)
        self.current.setCurrentRow(target)

    def _on_caption_edited(self, text: str) -> None:
        entry = self.current.currentItem()
        if entry is None:
            return
        item = entry.data(_ITEM_ROLE)
        if not item.action:
            return
        renamed = ToolItem(item.action, item.image, text)
        entry.setData(_ITEM_ROLE, renamed)
        entry.setText(text or item.action)

    def _on_restore(self) -> None:
        self.current.clear()
        for item in QUICK_ITEMS:
            self.current.addItem(_row(item))
        self._sync()

    def _sync(self) -> None:
        entry = self.current.currentItem()
        item = entry.data(_ITEM_ROLE) if entry is not None else None
        editable = item is not None and bool(item.action)
        self.caption.setEnabled(editable)
        self.caption.setText(item.caption if editable else "")
        self.remove_button.setEnabled(entry is not None)
        self.up_button.setEnabled(self.current.currentRow() > 0)
        self.down_button.setEnabled(
            0 <= self.current.currentRow() < self.current.count() - 1
        )


def _row(item: ToolItem) -> QListWidgetItem:
    if not item.action:
        entry = QListWidgetItem("──────────")
        entry.setData(_ITEM_ROLE, item)
        return entry
    entry = QListWidgetItem(R.get_icon(item.image), item.caption)
    entry.setData(_ITEM_ROLE, item)
    return entry


def _titled(title: str, widget: QWidget) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel(title)
    label.setStyleSheet("font-weight: bold;")
    layout.addWidget(label)
    layout.addWidget(widget)
    return box
