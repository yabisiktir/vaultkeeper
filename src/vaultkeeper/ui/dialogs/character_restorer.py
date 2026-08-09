"""Saving the characters you played with (VB Create Restorer, character option).

Shown when there are character files in the game that no mod owns — which is
what a character you rolled yourself looks like. Each becomes a restorer mod
holding a copy of its files, so reinstalling or moving on does not lose the
build.

One row per character rather than VB's one dialog after another: the names are
all pre-filled, the common case is to accept them, and a queue of modal prompts
is a poor way to say "these four, please".
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R


class CharacterRestorerDialog(QDialog):
    """Pick which characters to save, and what to call each restorer."""

    def __init__(self, groups: list, prefix: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._groups = list(groups)

        self.setWindowTitle("Create Character Restorer")
        self.setWindowIcon(R.get_icon("Windows_Seven_Icon_63_003"))
        geometry.remember(self, "CharacterRestorerDialog", 560, 340)

        layout = QVBoxLayout(self)
        heading = QLabel(
            f"{len(self._groups)} character(s) in your game belong to no mod."
        )
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)
        note = QLabel(
            "A Character Restorer keeps a copy of the build you played, so it "
            "survives reinstalling. Nothing is removed from the game. Double-click "
            "a name to change it."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        from vaultkeeper.game.character_restorer import restorer_name

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Restorer name", "Character", "Files"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for group in self._groups:
            item = QTreeWidgetItem(
                [restorer_name(prefix, group.name), group.name, str(group.count)]
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setToolTip(1, "\n".join(sorted(f.filename for f in group.files)))
            self.table.addTopLevelItem(item)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self) -> list[tuple[str, tuple]]:
        """``(restorer name, files)`` for each ticked row, names as edited."""
        picked = []
        for index, group in enumerate(self._groups):
            item = self.table.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked:
                name = item.text(0).strip()
                if name:
                    picked.append((name, group.files))
        return picked
