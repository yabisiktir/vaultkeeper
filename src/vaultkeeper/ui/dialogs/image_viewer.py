"""ImageViewer — a simple image preview (VB ``MsgPicture`` / ``OpenImage``).

Shows a single image scaled to fit, used by the Contents pane's "Display Info"
for loadscreen/portrait/texture files. NWN's native ``.tga`` images are decoded by
the bundled :class:`TGAReader`; other formats load through Qt's own image support.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.formats.tga_reader import TGAReader

#: Image extensions "Display Info" can preview.
IMAGE_EXTENSIONS = (".tga", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".dds")

_MAX = 640  # px — the preview box scales the image to fit within this.


def load_pixmap(path: Path, *, box: int = _MAX) -> QPixmap | None:
    """Load ``path`` as a QPixmap scaled to fit ``box`` (``None`` on failure)."""
    path = Path(path)
    if path.suffix.lower() == ".tga":
        image = TGAReader().read_file(path)
        if image is None or image.width <= 0 or image.height <= 0:
            return None
        qimg = QImage(
            image.to_rgba(), image.width, image.height, QImage.Format.Format_RGBA8888
        )
        pixmap = QPixmap.fromImage(qimg) if not qimg.isNull() else None
    else:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            pixmap = None
    if pixmap is None:
        return None
    return pixmap.scaled(
        box,
        box,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class ImageViewer(QDialog):
    """A scaled preview of a single image file."""

    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        path = Path(path)
        self.setWindowTitle(path.name)

        layout = QVBoxLayout(self)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = load_pixmap(path)
        if pixmap is not None:
            self._label.setPixmap(pixmap)
        else:
            self._label.setText(f"Unable to display {path.name}.")
        layout.addWidget(self._label, 1)

        bar = QHBoxLayout()
        bar.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bar.addWidget(close)
        layout.addLayout(bar)

    @classmethod
    def show_for(cls, path: Path, parent: QWidget | None = None) -> ImageViewer:
        dlg = cls(path, parent)
        dlg.show()
        return dlg
