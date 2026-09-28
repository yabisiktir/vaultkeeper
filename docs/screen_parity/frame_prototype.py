"""Preview NIT's dialog frame on real Vaultkeeper dialogs (see DIALOG_FRAME.md).

Run through the sandbox wrapper, from vaultkeeper/:
    VK_SCRIPT=frame_prototype.py docs/screen_parity/run_vk_shots.sh

Writes docs/screen_parity/frame/<Form>.png: the dialog as it is, with NIT's
header only (option A), and with NIT's whole frame (option B), side by side,
light theme then dark. A prototype: it rearranges finished dialogs from the
outside and touches no production code. What it builds (a header strip; a footer
band holding the status on the left and the buttons on the right, with Help
moved into the header's "?") is what ui/dialog_frame.py would provide.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

HERE = Path(__file__).resolve().parent
OUT = HERE / "frame"
sys.path.insert(0, str(HERE))

#: Form → (NIT header icon, NIT description, start of the VK label that becomes
#: the footer status, or None). Icons and texts are NIT's (frame_inventory.md).
FORMS = {
    "HakPatchEditor": (
        "OrderedList_32x",
        "Define the order in which hak patch files are applied. You only need to change "
        "the priority to deal with conflicts.",
        "Patch hak files detected",
    ),
    "AliasSectionEditor": (
        "open_folder",
        "Specify the location of the folders defined in the Alias Section of the NWN.ini "
        "file. You only need to change these entries if you have moved folders from the "
        "installation folder to another location.",
        None,
    ),
    "WorkshopViewer": (
        "SteamViewer32x",
        "View information about your Steam Workshop Subscriptions",
        "Steam Workshop Subscriptions detected",
    ),
}


def header(icon: str, text: str, help_button: QPushButton | None) -> QWidget:
    """NIT's header: 32 px icon, the description, and the round "?" at the right."""
    from vaultkeeper.ui import resources as R

    strip = QWidget()
    row = QHBoxLayout(strip)
    row.setContentsMargins(3, 3, 3, 3)
    picture = QLabel()
    picture.setPixmap(R.get_icon(icon).pixmap(32, 32))
    picture.setAlignment(Qt.AlignmentFlag.AlignTop)
    row.addWidget(picture)
    description = QLabel(text)
    description.setWordWrap(True)
    row.addWidget(description, 1)
    ask = QToolButton()
    ask.setIcon(R.get_icon("HelpIcon"))
    ask.setAutoRaise(True)
    ask.setToolTip("Help")
    if help_button is not None:
        ask.clicked.connect(help_button.click)
    row.addWidget(ask, 0, Qt.AlignmentFlag.AlignTop)
    return strip


def _footer_layout(outer: QVBoxLayout) -> QHBoxLayout | None:
    for i in range(outer.count() - 1, -1, -1):
        item = outer.itemAt(i).layout()
        if isinstance(item, QHBoxLayout):
            return item
    return None


def dress(dialog: QWidget, form: str, option: str) -> None:
    """Apply option "A" (header) or "B" (header + footer band) to ``dialog``."""
    icon, text, status_prefix = FORMS[form]
    outer = dialog.layout()
    buttons = [b for b in dialog.findChildren(QPushButton) if b.text() == "Help"]
    help_button = buttons[0] if buttons else None
    labels = [w for w in dialog.findChildren(QLabel) if w.parent() is dialog]
    status_label = next(
        (w for w in labels if status_prefix and w.text().startswith(status_prefix)), None
    )
    # The dialog's own description line gives way to the header's.
    if labels and labels[0] is not status_label:
        labels[0].hide()
    outer.insertWidget(0, header(icon, text, help_button))
    if option == "A":
        return
    if help_button is not None:
        help_button.hide()  # it is the header's "?" now
    footer = _footer_layout(outer)
    if footer is None:
        return
    band = QWidget()
    band.setAutoFillBackground(True)
    # NIT's footer is a WhiteSmoke band: a shade off the window colour, either theme.
    palette = band.palette()
    window = palette.color(QPalette.ColorRole.Window)
    shade = window.lighter(125) if window.lightness() < 128 else window.darker(106)
    palette.setColor(QPalette.ColorRole.Window, shade)
    band.setPalette(palette)
    row = QHBoxLayout(band)
    row.setContentsMargins(3, 3, 3, 3)
    status = QLabel(status_label.text() if status_label is not None else "")
    if status_label is not None:
        status_label.hide()
    row.addWidget(status, 1)
    for i in reversed(range(footer.count())):
        widget = footer.itemAt(i).widget()
        footer.takeAt(i)
        if isinstance(widget, QPushButton) and widget.isVisibleTo(dialog):
            row.insertWidget(1, widget)
    outer.removeItem(footer)
    outer.addWidget(band)


def triptych(images: list[tuple[str, QPixmap]], background: QColor) -> QPixmap:
    width = sum(p.width() for _t, p in images) + 20 * (len(images) + 1)
    height = max(p.height() for _t, p in images) + 50
    canvas = QPixmap(width, height)
    canvas.fill(background)
    painter = QPainter(canvas)
    painter.setPen(QColor("black") if background.lightness() > 128 else QColor("white"))
    x = 20
    for title, pix in images:
        painter.drawText(x, 28, title)
        painter.drawPixmap(x, 40, pix)
        x += pix.width() + 20
    painter.end()
    return canvas


def main() -> None:
    import vk_shots

    app = QApplication.instance() or QApplication([])
    from vaultkeeper.ui.theme import apply_appearance

    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        vk_shots._isolate(Path(tmp))
        c = vk_shots._controller(Path(tmp))
        assert str(c.ctx.game_user_dir).startswith(tmp)
        builders = vk_shots._builders(c)
        for theme in ("light", "dark"):
            apply_appearance(app, font_point_size=0, theme=theme)
            for form in FORMS:
                shots = []
                for option, title in (
                    ("", "As it is (kept, 2026-09-28)"),
                    ("A", "A: NIT header"),
                    ("B", "B: NIT header + footer"),
                ):
                    dialog = builders[form]()
                    if option:
                        dress(dialog, form, option)
                    dialog.resize(560, 420)
                    dialog.show()
                    app.processEvents()
                    shots.append((title, dialog.grab()))
                    dialog.close()
                bg = app.palette().color(QPalette.ColorRole.Window)
                triptych(shots, bg).save(str(OUT / f"{form}-{theme}.png"))
                print(f"{form} ({theme}): ok")


if __name__ == "__main__":
    main()
