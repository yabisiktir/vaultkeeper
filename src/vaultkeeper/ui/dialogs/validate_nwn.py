"""Validate Neverwinter Nights — files in the game that it has no use for.

VB shows a list and a *Delete Illegal Files* button that moves **the whole list**
to the recycle bin. Run against a real installation, that list was four files and
every one of them was legitimate: PRC's ``.hif`` hakpak-information files, and
the ``repository.json`` the game itself writes into ``mod`` and ``nwm``. So the
list here is a set of tick boxes, **all clear to begin with**, and the button
deletes what has been ticked.

"The game does not read this extension" is a fair thing to point out and a poor
thing to act on unasked.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R

_PATH_ROLE = Qt.ItemDataRole.UserRole


class ValidateNwnDialog(QDialog):
    """The findings, with a tick box each and nothing ticked."""

    def __init__(self, report: dict, controller=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller

        self.setWindowTitle("Validate Neverwinter Nights")
        self.setWindowIcon(R.get_icon("FindinFiles_6299"))
        geometry.remember(self, "ValidateNwnDialog", 660, 420)

        layout = QVBoxLayout(self)
        self.summary = QLabel(report.get("message", ""))
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        note = QLabel(
            "These are files in a folder the game reads, with an extension the "
            "game does not. That is worth knowing and is not the same as being "
            "junk — PRC's .hif files and the game's own repository.json both "
            "show up here. Tick only what you actually want gone."
        )
        note.setWordWrap(True)
        note.setEnabled(False)
        layout.addWidget(note)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["File", "Folder", "Size"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row in report.get("rows", []):
            item = QTreeWidgetItem([row["filename"], row["folder"], f"{row['size']:,} bytes"])
            item.setData(0, _PATH_ROLE, row["path"])
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self.table.addTopLevelItem(item)
        self.table.itemChanged.connect(lambda *_a: self._sync())
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.delete_button = QPushButton("Delete Ticked Files")
        self.delete_button.clicked.connect(self._on_delete)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._sync()

    def _ticked(self) -> list[str]:
        return [
            self.table.topLevelItem(i).data(0, _PATH_ROLE)
            for i in range(self.table.topLevelItemCount())
            if self.table.topLevelItem(i).checkState(0) == Qt.CheckState.Checked
        ]

    def _sync(self) -> None:
        self.delete_button.setEnabled(bool(self._ticked()) and self._controller is not None)

    def _on_delete(self) -> None:
        ticked = self._ticked()
        if self._controller is None or not ticked:
            return
        if (
            QMessageBox.question(
                self,
                "Validate Neverwinter Nights",
                f"Move {len(ticked)} file(s) out of your Neverwinter Nights folders?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.delete_illegal_game_files(ticked)
        report = self._controller.validate_neverwinter_nights()
        self.table.clear()
        for row in report["rows"]:
            item = QTreeWidgetItem([row["filename"], row["folder"], f"{row['size']:,} bytes"])
            item.setData(0, _PATH_ROLE, row["path"])
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self.table.addTopLevelItem(item)
        self.summary.setText(result["message"])
        self._sync()

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> ValidateNwnDialog:
        dlg = cls(controller.validate_neverwinter_nights(), controller, parent)
        dlg.show()
        return dlg
