#!/usr/bin/env python3
"""Draw the Vaultkeeper application icon at every size an installer needs.

Vector-drawn rather than scaled from a bitmap: macOS asks for 1024x1024 and
Windows for 256, and the artwork inherited from the old tool tops out at 64, so
anything derived from it is a 16x upscale — soft exactly where an icon is looked
at most, the Dock and the Finder.

The mark is a shield with a keyhole: Vaultkeeper guards an install and can put
it back. Drawn in the same plaque and palette as the save editor's icon so the
two read as one family, since Vaultkeeper ships the editor inside it.

Rendering per size rather than scaling one image keeps the small sizes legible —
a shrunk 1024 turns to mush, and the artwork inherited from the old tool tops out
at 64 anyway.

    python scripts/make_icons.py            # writes assets/icons/
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"

#: Straight from the editor's dark palette, so the app and its icon agree.
BG_TOP = "#1a120a"
BG_BOTTOM = "#0d0805"
GOLD = "#deaf56"
GOLD_DEEP = "#a87b2e"
PARCHMENT = "#f0e4cd"
INK = "#1a1408"

#: What each platform wants. macOS needs the @2x sizes for Retina.
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)


def draw(size: int) -> QImage:
    """The icon at one size, drawn for that size rather than scaled down.

    Composed for the smallest size first: a shield is one bold silhouette, so it
    still reads at 16px where anything layered would merge. The keyhole is the
    only interior detail and it is dropped below 48, where it would close up.
    """
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = size / 1024.0  # one design unit; the art is authored at 1024

    # -- rounded plaque, identical to the editor's ------------------------- #
    radius = 220 * u
    body = QRectF(40 * u, 40 * u, size - 80 * u, size - 80 * u)
    fill = QLinearGradient(body.topLeft(), body.bottomRight())
    fill.setColorAt(0.0, QColor(BG_TOP))
    fill.setColorAt(1.0, QColor(BG_BOTTOM))
    p.setBrush(QBrush(fill))
    p.setPen(QPen(QColor(GOLD_DEEP), max(1.0, 14 * u)))
    p.drawRoundedRect(body, radius, radius)

    # -- the shield -------------------------------------------------------- #
    shield = QPainterPath()
    top, left, right, point = 236 * u, 288 * u, 736 * u, 812 * u
    shield.moveTo(QPointF(left, top))
    shield.lineTo(QPointF(right, top))
    shield.lineTo(QPointF(right, 520 * u))
    # the two lower edges sweep in to a point, which is what makes it a shield
    shield.cubicTo(QPointF(right, 660 * u), QPointF(640 * u, 752 * u),
                   QPointF(512 * u, point))
    shield.cubicTo(QPointF(384 * u, 752 * u), QPointF(left, 660 * u),
                   QPointF(left, 520 * u))
    shield.closeSubpath()

    p.setPen(Qt.PenStyle.NoPen)
    face = QLinearGradient(QPointF(left, top), QPointF(right, point))
    face.setColorAt(0.0, QColor(GOLD))
    face.setColorAt(1.0, QColor(GOLD_DEEP))
    p.setBrush(QBrush(face))
    p.drawPath(shield)

    # -- keyhole: the one interior detail, and only where it fits ---------- #
    if size >= 48:
        p.setBrush(QColor(BG_BOTTOM))
        p.drawEllipse(QPointF(512 * u, 452 * u), 74 * u, 74 * u)
        stem = QPainterPath()
        stem.moveTo(QPointF(466 * u, 500 * u))
        stem.lineTo(QPointF(558 * u, 500 * u))
        stem.lineTo(QPointF(536 * u, 650 * u))
        stem.lineTo(QPointF(488 * u, 650 * u))
        stem.closeSubpath()
        p.drawPath(stem)

    p.end()
    return image


def write_pngs() -> dict[int, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    written = {}
    for size in SIZES:
        path = OUT / f"icon_{size}.png"
        draw(size).save(str(path), "PNG")
        written[size] = path
    return written


def write_ico(pngs: dict[int, Path]) -> Path:
    """A multi-size .ico — Windows picks the right one per context."""
    target = OUT / "icon.ico"
    images = [draw(s) for s in (16, 32, 48, 64, 128, 256)]
    # Qt writes a single image per file, so assemble the directory by hand.
    import struct

    encoded = []
    for image in images:
        buffer = OUT / f"_tmp_{image.width()}.png"
        image.save(str(buffer), "PNG")
        encoded.append((image.width(), buffer.read_bytes()))
        buffer.unlink()

    header = struct.pack("<HHH", 0, 1, len(encoded))
    offset = 6 + 16 * len(encoded)
    entries, blobs = b"", b""
    for width, data in encoded:
        side = 0 if width >= 256 else width
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    target.write_bytes(header + entries + blobs)
    return target


def write_icns(pngs: dict[int, Path]) -> Path | None:
    """A macOS .icns via iconutil, which needs a correctly named iconset."""
    if sys.platform != "darwin":
        return None
    iconset = OUT / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    # (size on disk, filename) — @2x entries are the Retina variants.
    wanted = [
        (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
    ]
    for size, name in wanted:
        draw(size).save(str(iconset / name), "PNG")
    target = OUT / "icon.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(target)], check=True
    )
    for leftover in iconset.iterdir():
        leftover.unlink()
    iconset.rmdir()
    return target


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    _ = app
    pngs = write_pngs()
    print(f"wrote {len(pngs)} PNGs -> {OUT}")
    print(f"wrote {write_ico(pngs).name}")
    icns = write_icns(pngs)
    print(f"wrote {icns.name}" if icns else "skipped .icns (needs macOS/iconutil)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
