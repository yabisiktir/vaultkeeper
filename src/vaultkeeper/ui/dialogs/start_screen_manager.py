"""StartScreenManager — browse NWN start-screen (loadscreen) images (VB StartScreenManager).

VB's Start Screen Manager lets the user manage the image NWN shows on its main
menu. This version is the gallery plus the auto-exclusion action: the NIT-managed
loadscreen images in a list (the active one marked, auto-excluded ones dimmed)
beside a preview of the selected image, with a status summary, and buttons to
toggle an image's auto-exclusion (VB RbAddAutoExclusion/RbRemoveAutoExclusion) or
clear all exclusions (VB RbInfoReport "Remove Exclusions").

The remaining actions — add-from-folder, add-from-hak (the extract-from-hak seam
is ready), install/uninstall/anneal, the slideshow and the prefix system — are
deferred.
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
    QPushButton,
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
    """Browse the managed loadscreen images with a preview + auto-exclusion action."""

    def __init__(
        self, report: dict, controller=None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("NWN Start Screen Manager")
        self.setWindowIcon(R.get_icon("Image"))
        self.resize(760, 520)
        self._controller = controller
        self._report = report
        self._images: list[dict] = report.get("images", [])

        outer = QVBoxLayout(self)

        panes = QHBoxLayout()
        outer.addLayout(panes, 1)

        self._list = QListWidget()
        self._list.setMinimumWidth(240)
        self._list.currentRowChanged.connect(self._on_row)
        panes.addWidget(self._list)

        right = QVBoxLayout()
        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(300)
        right.addWidget(self._preview, 1)
        self._detail = QLabel()
        self._detail.setWordWrap(True)
        right.addWidget(self._detail)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        right.addWidget(self._summary)
        panes.addLayout(right, 1)

        # Action buttons (only useful with a controller to act through).
        buttons = QHBoxLayout()
        self._exclude_btn = QPushButton("Toggle Auto-Exclude")
        self._exclude_btn.setToolTip(
            "Exclude/include the selected image from the slideshow and auto-select"
        )
        self._exclude_btn.clicked.connect(self._on_toggle_exclude)
        self._clear_btn = QPushButton("Clear Exclusions")
        self._clear_btn.clicked.connect(self._on_clear_exclusions)
        buttons.addWidget(self._exclude_btn)
        buttons.addWidget(self._clear_btn)
        buttons.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        outer.addLayout(buttons)

        self._populate()

    # -- Population -------------------------------------------------------- #
    def _populate(self, select: str | None = None) -> None:
        """Fill the list from the current report, optionally reselecting ``select``."""
        self._list.blockSignals(True)
        self._list.clear()
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
        self._list.blockSignals(False)

        self._summary.setText(self._report.get("summary", ""))
        has_controller = self._controller is not None
        self._clear_btn.setEnabled(
            has_controller and self._report.get("excluded_count", 0) > 0
        )

        if self._images:
            target = 0
            if select is not None:
                for i, row in enumerate(self._images):
                    if row["name"] == select:
                        target = i
                        break
            self._list.setCurrentRow(target)
        else:
            self._preview.setText("No loadscreen images to display.")
            self._exclude_btn.setEnabled(False)

    def _on_row(self, row: int) -> None:
        self._preview.clear()
        self._detail.clear()
        if row < 0 or row >= len(self._images):
            self._exclude_btn.setEnabled(False)
            return
        entry = self._images[row]
        self._exclude_btn.setEnabled(self._controller is not None)
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

    # -- Actions ----------------------------------------------------------- #
    def _current_entry(self) -> dict | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._images):
            return self._images[row]
        return None

    def _refresh(self, select: str | None = None) -> None:
        self._report = self._controller.loadscreens_report()
        self._images = self._report.get("images", [])
        self._populate(select=select)

    def _on_toggle_exclude(self) -> None:
        if self._controller is None:
            return
        entry = self._current_entry()
        if entry is None:
            return
        name = entry["name"]
        if entry["excluded"]:
            self._controller.remove_loadscreen_exclusion(name)
        else:
            self._controller.add_loadscreen_exclusion(name)
        self._refresh(select=name)

    def _on_clear_exclusions(self) -> None:
        if self._controller is None:
            return
        entry = self._current_entry()
        select = entry["name"] if entry else None
        self._controller.clear_loadscreen_exclusions()
        self._refresh(select=select)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> StartScreenManager:
        """Build and show the manager for the controller's loadscreen report."""
        dlg = cls(controller.loadscreens_report(), controller, parent)
        dlg.show()
        return dlg
