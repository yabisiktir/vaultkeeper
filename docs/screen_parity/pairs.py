"""Side-by-side NIT | VK images for each screen: docs/screen_parity/pairs/<Form>.png."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

HERE = Path(__file__).resolve().parent


def main(wanted: list[str]) -> None:
    QApplication.instance() or QApplication([])
    out = HERE / "pairs"
    out.mkdir(exist_ok=True)
    for nit in sorted((HERE / "nit").glob("*.png")):
        name = nit.stem
        vk = HERE / "vk" / f"{name}.png"
        if (wanted and name not in wanted) or not vk.exists():
            continue
        a, b = QImage(str(nit)), QImage(str(vk))
        gap, head = 16, 22
        img = QImage(a.width() + b.width() + gap, max(a.height(), b.height()) + head,
                     QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        p.setPen(QColor("black"))
        p.drawText(4, 16, f"NIT  {name}")
        p.drawText(a.width() + gap + 4, 16, "Vaultkeeper")
        p.drawImage(0, head, a)
        p.drawImage(a.width() + gap, head, b)
        p.fillRect(a.width() + gap // 2 - 1, 0, 2, img.height(), QColor(Qt.GlobalColor.red))
        p.end()
        img.save(str(out / f"{name}.png"))
        print(name)


if __name__ == "__main__":
    main(sys.argv[1:])
