"""A game save's screen image shown on hover (VB ``ImageToolTip`` / ``ScreenTip``).

NIT shows the save's ``screen.tga`` when you hover over *Manage your Game Saves*
(the latest save, ``BehaviourScreenTip``), the Game Saves Manager's location, and
a save's Character Summary text (``BehaviourScreenTipChar``). The image is
cropped top and bottom by ``ConfigSaveScreenCrop`` ("24, 88" by default), which
trims the game's own interface bars from the screenshot.

:class:`ScreenTip` is an event filter: it replaces a widget's tooltip with the
picture while the pointer rests on it, and hides it when the pointer leaves.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

#: NIT's default crop, top and bottom, in pixels (``ConfigSaveScreenCrop``).
DEFAULT_CROP = "24, 88"
#: VB ``ValidateScreenCrop``: each value may be at most 256 - 50.
MAX_CROP = 206
#: NIT shows the image for 20 seconds (``ScreenTip.Show(..., 20000)``).
SHOW_MS = 20000


def parse_crop(text: str) -> tuple[int, int] | None:
    """``"top, bottom"`` as two pixel counts, or ``None`` if it is not valid.

    VB ``ValidateScreenCrop``: one comma, whole numbers from 0 to 206.
    """
    parts = [p.strip() for p in (text or "").split(",")]
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    top, bottom = int(parts[0]), int(parts[1])
    if top > MAX_CROP or bottom > MAX_CROP:
        return None
    return top, bottom


def crop_values(text: str) -> tuple[int, int]:
    """The crop to use: ``text`` if valid, else NIT's default."""
    return parse_crop(text) or parse_crop(DEFAULT_CROP)


def screen_pixmap(path: Path, crop: tuple[int, int] = (0, 0)) -> QPixmap | None:
    """A save's ``screen.tga`` with ``crop`` pixels trimmed top and bottom."""
    from nwnfile.formats.tga_reader import TGAReader

    path = Path(path)
    if not path.is_file():
        return None
    image = TGAReader().read_file(path)
    if image is None or image.width <= 0 or image.height <= 0:
        return None
    data = image.to_rgba()  # QImage borrows this buffer; copy() below detaches it
    qimg = QImage(data, image.width, image.height, QImage.Format.Format_RGBA8888)
    if qimg.isNull():
        return None
    top, bottom = crop
    if top + bottom >= image.height:
        top = bottom = 0
    return QPixmap.fromImage(qimg.copy(0, top, image.width, image.height - top - bottom))


class ScreenTip(QObject):
    """Show a save's screen image instead of ``widget``'s tooltip.

    ``image_for(pos)`` gives the ``screen.tga`` for a point in the widget (or
    ``None`` for no image there); ``enabled()`` is read on every hover, so a
    Settings change applies at once; ``crop()`` gives the crop text.
    """

    def __init__(
        self,
        widget: QWidget,
        image_for: Callable[[QPoint], Path | None],
        *,
        enabled: Callable[[], bool] = lambda: True,
        crop: Callable[[], str] = lambda: DEFAULT_CROP,
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self._image_for = image_for
        self._enabled = enabled
        self._crop = crop
        self.popup = QLabel(None, Qt.WindowType.ToolTip)
        self.popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.popup.hide)
        widget.installEventFilter(self)
        widget.destroyed.connect(self.popup.deleteLater)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            return self.show_at(event.pos(), event.globalPos())
        if kind in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Hide):
            self.hide()
        return False

    def show_at(self, pos: QPoint, global_pos: QPoint) -> bool:
        """Show the image for ``pos``; False (keep the normal tooltip) if there is none."""
        if not self._enabled():
            return False
        path = self._image_for(pos)
        pixmap = screen_pixmap(path, crop_values(self._crop())) if path else None
        if pixmap is None:
            self.hide()
            return False
        self.popup.setPixmap(pixmap)
        self.popup.adjustSize()
        self.popup.move(global_pos + QPoint(16, 20))
        self.popup.show()
        self._timer.start(SHOW_MS)
        return True

    def hide(self) -> None:
        self._timer.stop()
        self.popup.hide()
