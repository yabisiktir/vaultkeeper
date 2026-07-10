"""StartScreenManager — browse NWN start-screen (loadscreen) images (VB StartScreenManager).

VB's Start Screen Manager lets the user manage the image NWN shows on its main
menu. This first version is the read-only gallery: the NIT-managed loadscreen
images in a list (the active one marked, auto-excluded ones dimmed) beside a
preview of the selected image, with a status summary.

The actions — add-from-folder, add-from-hak (the extract-from-hak seam is ready),
install/uninstall/anneal, the slideshow and the prefix system — are deferred.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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

#: The preview is scaled to fit this box; loadscreens are wide, so max dim is width.
_PREVIEW_BOX = 480

# Dimmed colour for auto-excluded images (won't be picked by the slideshow).
_EXCLUDED_COLOUR = QColor(150, 150, 150)


class StartScreenManager(QDialog):
    """Browse the managed loadscreen images with a preview of the selected one."""

    def __init__(self, report: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NWN Start Screen Manager")
        self.setWindowIcon(R.get_icon("Image"))
        self.resize(760, 480)
        self._report = report
        self._images: list[dict] = report.get("images", [])

        layout = QHBoxLayout(self)

        self._list = QListWidget()
        self._list.setMinimumWidth(240)
        for row in self._images:
            label = row["name"]
            if row["active"]:
                label = f"★ {label}"  # ★ active image
            item = QListWidgetItem(label)
            if row["excluded"]:
                item.setForeground(_EXCLUDED_COLOUR)
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
                item.setToolTip("Auto-excluded (skipped by the slideshow)")
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_row)
        layout.addWidget(self._list)

        right = QVBoxLayout()
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(300)
        right.addWidget(self._preview, 1)
        self._detail = QLabel()
        self._detail.setWordWrap(True)
        right.addWidget(self._detail)
        self._summary = QLabel(report.get("summary", ""))
        self._summary.setWordWrap(True)
        right.addWidget(self._summary)
        layout.addLayout(right, 1)

        if self._images:
            self._list.setCurrentRow(0)
        else:
            self._preview.setText("No loadscreen images to display.")

    def _on_row(self, row: int) -> None:
        self._preview.clear()
        self._detail.clear()
        if row < 0 or row >= len(self._images):
            return
        entry = self._images[row]
        pixmap = tga_to_pixmap(Path(entry["path"]), box=_PREVIEW_BOX)
        if pixmap is not None:
            self._preview.setPixmap(pixmap)
        else:
            self._preview.setText("(unable to preview this image)")

        flags = []
        if entry["active"]:
            flags.append("active")
        if entry["excluded"]:
            flags.append("auto-excluded")
        suffix = f"  — {', '.join(flags)}" if flags else ""
        self._detail.setText(f"{entry['name']}  ({entry['size_text']}){suffix}")

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> StartScreenManager:
        """Build and show the manager for the controller's loadscreen report."""
        dlg = cls(controller.loadscreens_report(), parent)
        dlg.show()
        return dlg
