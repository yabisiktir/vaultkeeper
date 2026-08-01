"""PortraitManager — manage the portraits your mods installed (VB PortraitManager).

Faithful to VB, the list is sourced from the profile's *installed* portraits
(``controller.installed_portraits_report`` → ``pd.InstalledList`` filtered to
portrait files), each tagged with the mod that installed it. The selected
portrait's five size thumbnails (tiny / small / medium / large / huge) are shown.
Actions: **Select** the portrait's mod in the main window (VB RbSelect), **Remove**
the portrait from the game + its mod's installer (VB Exclude / Apply-Excludes —
bounded: the port removes the file rather than persisting a Wizard exclude), and
**Extract from Hak…** (pull portrait sets out of a ``.hak``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nwnfile.character import PORTRAIT_SIZES
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.character_viewer import tga_to_pixmap
from vaultkeeper.ui.dialogs.help_viewer import help_button

_SIZE_BOXES = {"t": 32, "s": 64, "m": 96, "l": 128, "h": 160}
_SIZE_LABELS = {"t": "Tiny", "s": "Small", "m": "Medium", "l": "Large", "h": "Huge"}
_ROLE = Qt.ItemDataRole.UserRole


class PortraitManager(QDialog):
    """Manage the portraits the profile's mods installed (VB PortraitManager)."""

    def __init__(
        self,
        controller,
        on_select: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._on_select = on_select
        self._entries = self._load_entries()
        self.setWindowIcon(R.get_icon("user"))
        self.resize(720, 480)

        layout = QVBoxLayout(self)
        panes = QHBoxLayout()
        layout.addLayout(panes, 1)

        # Portrait list grouped by installing mod (VB portraits ordered by source mod).
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Portrait", "Mod"])
        self._tree.setMinimumWidth(300)
        self._tree.setRootIsDecorated(False)
        self._tree.currentItemChanged.connect(self._on_row)
        panes.addWidget(self._tree)

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
            col.addWidget(QLabel(_SIZE_LABELS[size], alignment=Qt.AlignmentFlag.AlignCenter))
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
        buttons.addStretch(1)
        self._select_button = QPushButton("Select")
        self._select_button.setToolTip("Select this portrait's mod in the main window")
        self._select_button.clicked.connect(self._on_select_mod)
        buttons.addWidget(self._select_button)
        self._remove_button = QPushButton("Remove")
        self._remove_button.setToolTip("Remove this portrait from the game and its mod's installer")
        self._remove_button.clicked.connect(self._on_remove)
        buttons.addWidget(self._remove_button)
        self._extract_button = QPushButton("Extract from Hak…")
        self._extract_button.clicked.connect(self._on_extract)
        self._extract_button.setEnabled(controller is not None)
        buttons.addWidget(self._extract_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._populate()

    def _load_entries(self) -> list[dict]:
        if self._controller is None:
            return []
        return self._controller.installed_portraits_report()["portraits"]

    def _populate(self, select: int = 0) -> None:
        self.setWindowTitle(
            f"Portrait Manager — Installed Portraits: {len(self._entries):,}"
            if self._entries
            else "Portrait Manager"
        )
        self._tree.blockSignals(True)
        self._tree.clear()
        for entry in self._entries:
            sizes = "".join(s for s in PORTRAIT_SIZES if s in entry["sizes"])
            item = QTreeWidgetItem([f"{entry['resref']}  [{sizes}]", entry["mod"]])
            item.setData(0, _ROLE, entry)
            self._tree.addTopLevelItem(item)
        self._tree.blockSignals(False)
        self._caption.setText(f"Installed portraits: {len(self._entries):,}")
        has = bool(self._entries)
        self._select_button.setEnabled(has)
        self._remove_button.setEnabled(has)
        if has:
            self._tree.setCurrentItem(
                self._tree.topLevelItem(min(select, len(self._entries) - 1))
            )

    def _current(self) -> dict | None:
        item = self._tree.currentItem()
        return item.data(0, _ROLE) if item is not None else None

    def _on_row(self, *_a) -> None:
        for image in self._thumbs.values():
            image.clear()
        entry = self._current()
        if entry is None:
            return
        for size in PORTRAIT_SIZES:
            path = entry["sizes"].get(size)
            if path is not None:
                pixmap = tga_to_pixmap(path, box=_SIZE_BOXES[size])
                if pixmap is not None:
                    self._thumbs[size].setPixmap(pixmap)

    def _on_select_mod(self) -> None:
        entry = self._current()
        if entry and entry.get("mod") and self._on_select is not None:
            self._on_select(entry["mod"])
            self.accept()

    def _on_remove(self) -> None:
        entry = self._current()
        if entry is None or self._controller is None:
            return
        if (
            QMessageBox.question(
                self,
                "Remove Portrait",
                f"Remove portrait '{entry['resref']}' from the game and "
                f"'{entry['mod']}'s installer?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.remove_installed_portrait(entry["resref"])
        self._entries = self._load_entries()
        self._populate()
        QMessageBox.information(self, "Portrait Manager", result.get("message", ""))

    def _on_extract(self) -> None:
        if self._controller is None:
            return
        from PySide6.QtWidgets import QFileDialog

        hak, _ = QFileDialog.getOpenFileName(
            self, "Select a hak file", "", "Hak files (*.hak);;All files (*)"
        )
        if not hak:
            return
        result = self._controller.extract_hak_portraits(Path(hak))
        self._entries = self._load_entries()
        self._populate()
        QMessageBox.information(self, "Portrait Manager", result.get("message", ""))

    @classmethod
    def show_for(
        cls, controller, on_select=None, parent: QWidget | None = None
    ) -> PortraitManager:
        """Build and show the manager for the controller's installed portraits."""
        dlg = cls(controller, on_select, parent)
        dlg.show()
        return dlg
