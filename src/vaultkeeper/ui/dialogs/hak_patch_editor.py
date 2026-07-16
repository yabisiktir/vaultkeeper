"""HakPatchEditor — order the patch-hak load sequence (VB ``HakPatchEditor``).

Neverwinter Nights loads "patch" haks (the ``.hak`` files installed into the game's
``patch`` folder) in the order listed in ``nwnpatch.ini``. This editor shows those
installed patch-haks and lets the user reorder them; **Save** persists the order to the
NIT-managed ``PatchFileSequence.txt`` and regenerates ``nwnpatch.ini`` so it takes
effect (VB ``HakPatchManager.UpdateSequenceFile`` + ``ValidateAll``).

Built on ``ProfileController.patch_hak_sequence`` / ``save_patch_hak_sequence``. Only
the sequence file (a NIT file) and NIT's own generated ``nwnpatch.ini`` are written —
no game *config* is touched, so no config-isolation prompt is needed.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R


class HakPatchEditor(QDialog):
    """Reorder the patch-hak load sequence."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Hak Patch Editor")
        self.setWindowIcon(R.get_icon("Hammer_Builder_16xLG"))
        self.resize(420, 420)

        outer = QVBoxLayout(self)
        self._count_label = QLabel("")
        outer.addWidget(self._count_label)

        body = QHBoxLayout()
        outer.addLayout(body, 1)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._update_buttons)
        body.addWidget(self.list, 1)

        side = QVBoxLayout()
        self.up_button = QPushButton("Move Up")
        self.up_button.clicked.connect(lambda: self._move(-1))
        self.down_button = QPushButton("Move Down")
        self.down_button.clicked.connect(lambda: self._move(1))
        side.addWidget(self.up_button)
        side.addWidget(self.down_button)
        side.addStretch(1)
        body.addLayout(side)

        buttons = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhHakPatchEditor", self))
        buttons.addStretch(1)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.save_button)
        buttons.addWidget(close_button)
        outer.addLayout(buttons)

        self._load()

    def _load(self) -> None:
        haks = self._controller.patch_hak_sequence()
        self.list.clear()
        self.list.addItems(haks)
        self._count_label.setText(
            f"Patch hak files detected: {len(haks) if haks else 'None'}."
        )
        if haks:
            self.list.setCurrentRow(0)
        # Reordering + saving only makes sense with two or more haks (VB rule).
        multi = len(haks) >= 2
        self.up_button.setVisible(multi)
        self.down_button.setVisible(multi)
        self.save_button.setEnabled(multi)
        self._update_buttons(self.list.currentRow())

    def _update_buttons(self, row: int) -> None:
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < self.list.count() - 1)

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)

    def order(self) -> list[str]:
        """The current patch-hak order shown in the list."""
        return [self.list.item(i).text() for i in range(self.list.count())]

    def _on_save(self) -> None:
        self._controller.save_patch_hak_sequence(self.order())
        self.accept()

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> HakPatchEditor:
        """Build and show the Hak Patch editor for a controller's profile."""
        dlg = cls(controller, parent)
        dlg.show()
        return dlg
