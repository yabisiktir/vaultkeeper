"""CharacterViewer — the Character Explorer / Character Summary dialog (VB CharacterViewer).

Lists the player's characters (local vault + one per game save) on the left and
shows the selected character's multi-line summary plus portrait on the right.
Read-only. Data comes from ``ProfileController.character_files`` /
``portrait_path``; the summary text is produced by ``game.character``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.formats.tga_reader import TGAReader
from vaultkeeper.ui import resources as R

_PORTRAIT_BOX = 128  # px — the portrait preview is a square this size.


def tga_to_pixmap(path: Path, *, box: int = _PORTRAIT_BOX) -> QPixmap | None:
    """Load a TGA portrait as a QPixmap scaled to fit ``box`` (None on failure)."""
    image = TGAReader().read_file(path)
    if image is None or image.width <= 0 or image.height <= 0:
        return None
    qimg = QImage(
        image.to_rgba(),
        image.width,
        image.height,
        QImage.Format.Format_RGBA8888,
    )
    if qimg.isNull():
        return None
    return QPixmap.fromImage(qimg).scaled(
        box,
        box,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class CharacterViewer(QDialog):
    """Browse characters with their summary and portrait."""

    def __init__(
        self, characters: list, portrait_resolver=None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Character Explorer")
        self.setWindowIcon(R.get_icon("LookupUser_16x"))
        self.resize(680, 460)
        self._characters = characters
        self._resolve_portrait = portrait_resolver

        layout = QHBoxLayout(self)

        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        for cf in characters:
            level = cf.info.level if cf.info.is_valid else "?"
            item = QListWidgetItem(f"{cf.display_name}  (L{level})")
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_row)
        layout.addWidget(self._list)

        right = QVBoxLayout()
        self._portrait = QLabel()
        self._portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._portrait.setFixedHeight(_PORTRAIT_BOX)
        right.addWidget(self._portrait)
        self._summary = QTextEdit()
        self._summary.setReadOnly(True)
        right.addWidget(self._summary)
        layout.addLayout(right, 1)

        if characters:
            self._list.setCurrentRow(0)
        else:
            self._summary.setPlainText("No character files detected.")

    def _on_row(self, row: int) -> None:
        if row < 0 or row >= len(self._characters):
            self._summary.clear()
            self._portrait.clear()
            return
        cf = self._characters[row]
        self._summary.setPlainText(cf.summary(show_stats=True))
        self._show_portrait(cf)

    def _show_portrait(self, cf) -> None:
        self._portrait.clear()
        resref = cf.info.portrait_resref if cf.info.is_valid else ""
        if not resref or self._resolve_portrait is None:
            return
        path = self._resolve_portrait(resref, cf.path.parent)
        if path is not None:
            pixmap = tga_to_pixmap(path)
            if pixmap is not None:
                self._portrait.setPixmap(pixmap)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> CharacterViewer:
        """Build and show the viewer from a controller's character files."""

        def resolver(resref: str, own_folder: Path):
            return controller.portrait_path(resref, extra_dirs=[own_folder])

        dlg = cls(controller.character_files(), resolver, parent)
        dlg.show()
        return dlg
