"""Classes, Skills and Feats reference viewer (VB ``ClassesSkillsAndFeats``).

A read-only reference: three tabs (Classes / Skills / Feats), each a searchable
name list beside a description panel. The data comes from the bundled reference
tables (``game/character_reference``), the same ``Feat/Skill/Class Names.txt`` +
``Descriptions.txt`` files the original app ships.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from nwnfile.character_reference import CharacterReference, default_reference
from vaultkeeper.ui import resources as R

_DESC_ROLE = Qt.ItemDataRole.UserRole


class _ReferenceTab(QWidget):
    """A search box + name list beside a description panel (VB Lv*/Lb* pair)."""

    def __init__(self, rows: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        for name, desc in rows:
            item = QListWidgetItem(name)
            item.setData(_DESC_ROLE, desc)
            self.list.addItem(item)
        self.list.currentItemChanged.connect(self._show_description)
        splitter.addWidget(self.list)

        self.description = QTextBrowser()
        self.description.setOpenExternalLinks(False)
        splitter.addWidget(self.description)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 400])
        layout.addWidget(splitter, 1)

        if self.list.count():
            self.list.setCurrentRow(0)

    def _show_description(self, current: QListWidgetItem | None) -> None:
        if current is None:
            self.description.clear()
            return
        # VB SetHeading prefixes the description with the item name.
        name = current.text()
        desc = current.data(_DESC_ROLE) or "Description is unavailable."
        self.description.setHtml(f"<h3>{name}</h3><p>{desc.replace(chr(10), '<br>')}</p>")

    def _filter(self, text: str) -> None:
        needle = text.casefold()
        first_visible: QListWidgetItem | None = None
        for i in range(self.list.count()):
            item = self.list.item(i)
            hidden = bool(needle) and needle not in item.text().casefold()
            item.setHidden(hidden)
            if not hidden and first_visible is None:
                first_visible = item
        # Keep a visible selection so the description panel stays meaningful.
        current = self.list.currentItem()
        if (current is None or current.isHidden()) and first_visible is not None:
            self.list.setCurrentItem(first_visible)


class ClassesSkillsAndFeatsDialog(QDialog):
    """Read-only Classes / Skills / Feats reference (VB ``ClassesSkillsAndFeats``)."""

    def __init__(
        self,
        reference: CharacterReference | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Classes, Skills and Feats")
        self.setWindowIcon(R.app_icon())
        self.resize(680, 480)
        reference = reference or default_reference()

        layout = QVBoxLayout(self)
        if not reference.available:
            layout.addWidget(
                QLabel("Class, skill and feat reference data is not available.")
            )
        else:
            self.tabs = QTabWidget()
            self.tabs.addTab(_ReferenceTab(reference.all_classes()), "Classes")
            self.tabs.addTab(_ReferenceTab(reference.all_skills()), "Skills")
            self.tabs.addTab(_ReferenceTab(reference.all_feats()), "Feats")
            layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    @classmethod
    def show_dialog(
        cls,
        reference: CharacterReference | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Construct and show the reference viewer (modal)."""
        cls(reference, parent).exec()
