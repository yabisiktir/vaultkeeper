"""StartScreenManager — browse NWN start-screen (loadscreen) images (VB StartScreenManager).

VB's Start Screen Manager lets the user manage the image NWN shows on its main
menu. The NIT-managed loadscreen images are shown in a list (the active one marked,
auto-excluded ones dimmed) beside a preview of the selected image, with a status
summary. Actions: **Install** the selected image as NWN's start screen (VB
RbInstall), **Add Folder…**/**Add Hak…** to import TGA images (VB
ProcessFolders/add-from-hak), **Delete** selected images (VB RbDeleteFile), and
toggle an image's auto-exclusion / clear all exclusions (VB
RbAddAutoExclusion/RbRemoveAutoExclusion/RbInfoReport).

Deferred: the slideshow, the prefix editor, and Rename (a VB bug landmine — see the
handoff).
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
        self.setWindowTitle("NWN's Start Screen Manager")
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
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
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
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("RbLoadscreenHelp", self))
        self._install_btn = QPushButton("Install")
        self._install_btn.setToolTip("Install the selected image as NWN's start screen")
        self._install_btn.clicked.connect(self._on_install)
        buttons.addWidget(self._install_btn)
        self._add_folder_btn = QPushButton("Add Folder…")
        self._add_folder_btn.setToolTip("Add all TGA images found under a folder")
        self._add_folder_btn.clicked.connect(self._on_add_folder)
        buttons.addWidget(self._add_folder_btn)
        self._add_hak_btn = QPushButton("Add Hak…")
        self._add_hak_btn.setToolTip("Add TGA images extracted from a .hak file")
        self._add_hak_btn.clicked.connect(self._on_add_hak)
        buttons.addWidget(self._add_hak_btn)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setToolTip("Delete the selected image(s)")
        self._delete_btn.clicked.connect(self._on_delete)
        buttons.addWidget(self._delete_btn)
        self._rename_btn = QPushButton("Rename…")
        self._rename_btn.setToolTip("Rename the selected image")
        self._rename_btn.clicked.connect(self._on_rename)
        buttons.addWidget(self._rename_btn)
        self._export_btn = QPushButton("Export…")
        self._export_btn.setToolTip("Copy the selected start screen image(s) to a folder")
        self._export_btn.clicked.connect(self._on_export)
        buttons.addWidget(self._export_btn)
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
            tips: list[str] = []
            if row["excluded"]:
                item.setForeground(_EXCLUDED_COLOUR)
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
                tips.append("Auto-excluded (skipped by the slideshow)")
            if row.get("prefixed"):
                tips.append(
                    "Prefixed (enabled)"
                    if row.get("filter_prefixed")
                    else "Prefixed (disabled)"
                )
            if tips:
                item.setToolTip(" · ".join(tips))
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
        self._update_action_state()

    def _on_row(self, row: int) -> None:
        self._preview.clear()
        self._detail.clear()
        if row < 0 or row >= len(self._images):
            self._exclude_btn.setEnabled(False)
            self._update_action_state()
            return
        entry = self._images[row]
        self._exclude_btn.setEnabled(self._controller is not None)
        self._update_action_state()
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
        if entry.get("prefixed"):
            flags.append(
                "prefixed" if entry.get("filter_prefixed") else "prefixed (disabled)"
            )
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

    def _on_install(self) -> None:
        """Install the selected image as NWN's start screen (VB RbInstall)."""
        if self._controller is None:
            return
        entry = self._current_entry()
        if entry is None:
            return
        name = entry["name"]
        result = self._controller.install_loadscreen(name)
        self._status(result.get("message", ""))
        self._refresh(select=name)

    def _on_add_folder(self) -> None:
        """Add TGA images found under a chosen folder (VB Add-from-Folders)."""
        if self._controller is None:
            return
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "Select a folder of TGA images")
        if not folder:
            return
        result = self._controller.add_loadscreen_folders([Path(folder)])
        self._status(result.get("message", ""))
        self._refresh()

    def _on_add_hak(self) -> None:
        """Add TGA images extracted from a chosen .hak file (VB Add-from-Hak)."""
        if self._controller is None:
            return
        from PySide6.QtWidgets import QFileDialog

        hak, _ = QFileDialog.getOpenFileName(
            self, "Select a hak file", "", "Hak files (*.hak);;All files (*)"
        )
        if not hak:
            return
        result = self._controller.add_loadscreen_from_hak(Path(hak))
        self._status(result.get("message", ""))
        self._refresh()

    def _on_delete(self) -> None:
        """Delete the selected image(s) (VB RbDeleteFile)."""
        if self._controller is None:
            return
        entries = [self._images[i.row()] for i in self._list.selectedIndexes()]
        if not entries:
            entry = self._current_entry()
            entries = [entry] if entry else []
        if not entries:
            return
        from PySide6.QtWidgets import QMessageBox

        names = [e["name"] for e in entries]
        plural = "image" if len(names) == 1 else "images"
        if (
            QMessageBox.question(
                self,
                "Delete Start Screen Images",
                f"Delete {len(names)} start screen {plural}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.delete_loadscreen_images(names)
        self._status(result.get("message", ""))
        self._refresh()

    def _on_export(self) -> None:
        """Export the selected image(s) to a chosen folder (VB RbExport)."""
        if self._controller is None:
            return
        entries = [self._images[i.row()] for i in self._list.selectedIndexes()]
        if not entries:
            entry = self._current_entry()
            entries = [entry] if entry else []
        if not entries:
            self._status("Select an image to export first.")
            return
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        target = QFileDialog.getExistingDirectory(self, "Export start screen images to…")
        if not target:
            return
        names = [e["name"] for e in entries]
        result = self._controller.export_loadscreen_images(names, Path(target))
        self._status(result.get("message", ""))

    def _on_rename(self) -> None:
        """Rename the selected image (VB RbRename — validation in the controller)."""
        if self._controller is None:
            return
        entry = self._current_entry()
        if entry is None:
            return
        from PySide6.QtWidgets import QInputDialog

        old = entry["name"]
        new, ok = QInputDialog.getText(self, "Rename Image File", "New name:", text=old)
        if not ok or not new:
            return
        result = self._controller.rename_loadscreen_image(old, new)
        self._status(result.get("message", ""))
        self._refresh(select=result.get("name", old))

    def _status(self, text: str) -> None:
        if text:
            self._summary.setText(text)

    def _update_action_state(self) -> None:
        has_controller = self._controller is not None
        has_selection = self._current_entry() is not None
        self._install_btn.setEnabled(has_controller and has_selection)
        self._delete_btn.setEnabled(has_controller and has_selection)
        self._rename_btn.setEnabled(has_controller and has_selection)
        self._add_folder_btn.setEnabled(has_controller)
        self._add_hak_btn.setEnabled(has_controller)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> StartScreenManager:
        """Build and show the manager for the controller's loadscreen report."""
        dlg = cls(controller.loadscreens_report(), controller, parent)
        dlg.show()
        return dlg
