"""PortraitManager — lists installed portraits and previews them (VB PortraitManager).

VB's Portrait Manager "displays the Medium and Huge images" of installed portrait
files. This first version is that read-only core: a list of installed portraits
(grouped by resref across the NWN portrait search folders) with a medium + huge
preview of the selected one. The heavier VB features (extract-from-hak, exclude,
web-image retrieval, assigning a start portrait) come later.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.character_viewer import tga_to_pixmap

_MEDIUM_BOX = 128
_HUGE_BOX = 256


class PortraitManager(QDialog):
    """Browse installed portraits with medium + huge previews."""

    def __init__(self, entries: list, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Portrait Manager")
        self.setWindowIcon(R.get_icon("user"))
        self.resize(620, 440)
        self._entries = entries

        layout = QHBoxLayout(self)

        self._list = QListWidget()
        self._list.setMinimumWidth(240)
        for entry in entries:
            sizes = "".join(s for s in ("t", "s", "m", "l", "h") if s in entry.sizes)
            item = QListWidgetItem(f"{entry.resref}  [{sizes}]")
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_row)
        layout.addWidget(self._list)

        right = QVBoxLayout()
        self._huge = QLabel()
        self._huge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._huge.setFixedHeight(_HUGE_BOX)
        right.addWidget(self._huge)
        self._medium = QLabel()
        self._medium.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._medium.setFixedHeight(_MEDIUM_BOX)
        right.addWidget(self._medium)
        self._caption = QLabel(f"Installed portraits: {len(entries):,}")
        right.addWidget(self._caption)
        layout.addLayout(right, 1)

        if entries:
            self._list.setCurrentRow(0)

    def _on_row(self, row: int) -> None:
        self._huge.clear()
        self._medium.clear()
        if row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]
        self._set_image(self._huge, entry.path("h"), _HUGE_BOX)
        self._set_image(self._medium, entry.path("m"), _MEDIUM_BOX)

    @staticmethod
    def _set_image(label: QLabel, path, box: int) -> None:
        if path is None:
            return
        pixmap = tga_to_pixmap(path, box=box)
        if pixmap is not None:
            label.setPixmap(pixmap)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> PortraitManager:
        """Build and show the manager for the controller's installed portraits."""
        dlg = cls(controller.portrait_entries(), parent)
        dlg.show()
        return dlg
