"""PortraitManager — browse installed portraits + extract from haks (VB PortraitManager).

Lists the installed portraits (grouped by resref across the NWN portrait search
folders) with the **five size thumbnails** (tiny / small / medium / large / huge) of
the selected one, and an **Extract from Hak…** action (VB extract-from-hak — pull
complete portrait sets out of a ``.hak`` via the ERF seam into the extracted-portraits
area). The web-image retrieval / exclude / assign-start-portrait features are deferred.
"""

from __future__ import annotations

from pathlib import Path

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

from vaultkeeper.game.character import PORTRAIT_SIZES
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.character_viewer import tga_to_pixmap
from vaultkeeper.ui.dialogs.help_viewer import help_button

#: Thumbnail box per size letter (t/s/m/l/h) — mirrors NWN's portrait size ladder.
_SIZE_BOXES = {"t": 32, "s": 64, "m": 96, "l": 128, "h": 160}
_SIZE_LABELS = {"t": "Tiny", "s": "Small", "m": "Medium", "l": "Large", "h": "Huge"}


class PortraitManager(QDialog):
    """Browse installed portraits with five-size thumbnails + extract-from-hak."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._entries = controller.portrait_entries() if controller else []
        self.setWindowIcon(R.get_icon("user"))
        self.resize(680, 460)

        layout = QVBoxLayout(self)
        panes = QHBoxLayout()
        layout.addLayout(panes, 1)

        self._list = QListWidget()
        self._list.setMinimumWidth(240)
        self._list.currentRowChanged.connect(self._on_row)
        panes.addWidget(self._list)

        # Five-size thumbnail row (VB shows the size variants side by side).
        right = QVBoxLayout()
        thumbs = QHBoxLayout()
        self._thumbs: dict[str, QLabel] = {}
        for size in PORTRAIT_SIZES:
            col = QVBoxLayout()
            image = QLabel()
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setFixedSize(_SIZE_BOXES[size] + 4, _SIZE_BOXES[size] + 4)
            self._thumbs[size] = image
            col.addWidget(image)
            col.addWidget(
                QLabel(_SIZE_LABELS[size], alignment=Qt.AlignmentFlag.AlignCenter)
            )
            col.addStretch(1)
            thumbs.addLayout(col)
        thumbs.addStretch(1)
        right.addLayout(thumbs)
        self._caption = QLabel()
        right.addWidget(self._caption)
        right.addStretch(1)
        panes.addLayout(right, 1)

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("RbPortraitManagerHelp", self))
        # VB RbPrevious / RbNext: step through the portrait list.
        self._prev_button = QPushButton("◀ Previous")
        self._prev_button.clicked.connect(lambda: self._step(-1))
        buttons.addWidget(self._prev_button)
        self._next_button = QPushButton("Next ▶")
        self._next_button.clicked.connect(lambda: self._step(1))
        buttons.addWidget(self._next_button)
        buttons.addStretch(1)
        self._extract_button = QPushButton("Extract from Hak…")
        self._extract_button.clicked.connect(self._on_extract)
        self._extract_button.setEnabled(controller is not None)
        buttons.addWidget(self._extract_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._populate()

    def _populate(self, select: int = 0) -> None:
        # VB title carries the count ("Portrait Manager — Installed Portraits: N").
        suffix = (
            f" — Installed Portraits: {len(self._entries):,}" if self._entries else ""
        )
        self.setWindowTitle(f"Portrait Manager{suffix}")
        self._list.blockSignals(True)
        self._list.clear()
        for entry in self._entries:
            sizes = "".join(s for s in PORTRAIT_SIZES if s in entry.sizes)
            self._list.addItem(QListWidgetItem(f"{entry.resref}  [{sizes}]"))
        self._list.blockSignals(False)
        self._caption.setText(f"Installed portraits: {len(self._entries):,}")
        if self._entries:
            self._list.setCurrentRow(min(select, len(self._entries) - 1))

    def _step(self, delta: int) -> None:
        """Move the selection by ``delta`` rows, clamped (VB RbPrevious/RbNext)."""
        if not self._entries:
            return
        row = self._list.currentRow()
        self._list.setCurrentRow(max(0, min(row + delta, len(self._entries) - 1)))

    def _on_row(self, row: int) -> None:
        for image in self._thumbs.values():
            image.clear()
        if row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]
        for size in PORTRAIT_SIZES:
            path = entry.sizes.get(size)
            if path is not None:
                pixmap = tga_to_pixmap(path, box=_SIZE_BOXES[size])
                if pixmap is not None:
                    self._thumbs[size].setPixmap(pixmap)

    def _on_extract(self) -> None:
        if self._controller is None:
            return
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        hak, _ = QFileDialog.getOpenFileName(
            self, "Select a hak file", "", "Hak files (*.hak);;All files (*)"
        )
        if not hak:
            return
        result = self._controller.extract_hak_portraits(Path(hak))
        self._entries = self._controller.portrait_entries()
        self._populate()
        QMessageBox.information(self, "Portrait Manager", result.get("message", ""))

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> PortraitManager:
        """Build and show the manager for the controller's installed portraits."""
        dlg = cls(controller, parent)
        dlg.show()
        return dlg
