"""GameSavesManager — the game-saves listing + archive dialog (VB ``GameManager``).

Lists the current NWN game saves (folder, save name, in-module location, save type,
size) with a summary line, plus the current game's archived save ranges. Offers the
**Reduce** action (archive the oldest saves, keeping the newest N — VB ``NudKeep`` /
``ArchiveGames``) and **Restore** (bring an archived range back — VB ``RestoreGames``),
driven through ``ProfileController``.

Bounded: the VB deactivate/activate/delete-game backup flows and the three-way
"already archived" prompt are not surfaced — a Reduce onto an existing range merges
into it (``on_existing="overwrite"``).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R


class GameSavesManager(QDialog):
    """A table of the current game saves, their archives, and Reduce/Restore."""

    def __init__(
        self, report: dict, controller=None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Game Saves Manager")
        self.setWindowIcon(R.get_icon("GameManager16"))
        self.resize(640, 520)

        layout = QVBoxLayout(self)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Folder", "Save Name", "Location", "Type", "Size"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.summary = QLabel()
        layout.addWidget(self.summary)

        # -- Reduce (archive the oldest saves) -------------------------------- #
        reduce_row = QHBoxLayout()
        reduce_row.addWidget(
            QLabel("Number of game saves to keep when you Reduce NWN game saves")
        )
        self.keep_spin = QSpinBox()
        self.keep_spin.setRange(30, 900)
        self.keep_spin.setSingleStep(20)
        self.keep_spin.setValue(100)
        reduce_row.addWidget(self.keep_spin)
        self.reduce_button = QPushButton("Reduce")
        self.reduce_button.clicked.connect(self._on_reduce)
        reduce_row.addWidget(self.reduce_button)
        layout.addLayout(reduce_row)

        # -- Archived ranges + Restore ---------------------------------------- #
        layout.addWidget(QLabel("Archived game saves"))
        self.archives = QTreeWidget()
        self.archives.setHeaderLabels(["Archived Range", "Saves", "Size"])
        self.archives.setRootIsDecorated(False)
        self.archives.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.archives.itemSelectionChanged.connect(self._sync_buttons)
        layout.addWidget(self.archives)

        button_row = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        button_row.addWidget(help_button("BhGameManager", self))
        button_row.addStretch(1)
        self.restore_button = QPushButton("Restore")
        self.restore_button.clicked.connect(self._on_restore)
        button_row.addWidget(self.restore_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._populate(report)

    # -- Rendering -------------------------------------------------------- #
    def _populate(self, report: dict) -> None:
        self.table.clear()
        for row in report.get("rows", []):
            self.table.addTopLevelItem(
                QTreeWidgetItem(
                    [row["name"], row["save"], row["location"], row["type"], row["size"]]
                )
            )

        count = report.get("count", 0)
        current = report.get("current") or "—"
        total = report.get("total_size") or "0 B"
        self.summary.setText(
            f"Saves: {count:,}    Current game: {current}    Total size: {total}"
        )

        self.archives.clear()
        for arc in report.get("archived", []):
            self.archives.addTopLevelItem(
                QTreeWidgetItem(
                    [arc["range"], f"{arc['count']:,}", arc["size"]]
                )
            )

        self.reduce_button.setEnabled(
            bool(self._controller) and report.get("can_reduce", False)
        )
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.restore_button.setEnabled(
            bool(self._controller) and self.archives.currentItem() is not None
        )

    def _refresh(self) -> None:
        if self._controller is not None:
            self._populate(self._controller.game_saves_report())

    # -- Actions ---------------------------------------------------------- #
    def _on_reduce(self) -> None:
        if self._controller is None:
            return
        keep = self.keep_spin.value()
        if (
            QMessageBox.question(
                self,
                "Reduce Game Saves",
                f"Archive the oldest game saves, keeping the newest {keep}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.reduce_game_saves(keep)
        self._refresh()
        self._report(result["message"], result["ok"])

    def _on_restore(self) -> None:
        item = self.archives.currentItem()
        if self._controller is None or item is None:
            return
        range_name = item.text(0)
        if (
            QMessageBox.question(
                self,
                "Restore Game Saves",
                f"Restore the archived game saves in {range_name}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.restore_archived_saves(range_name)
        self._refresh()
        self._report(result["message"], result["ok"])

    def _report(self, message: str, ok: bool) -> None:
        if ok:
            QMessageBox.information(self, "Game Saves Manager", message)
        else:
            QMessageBox.warning(self, "Game Saves Manager", message)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> GameSavesManager:
        """Build and show the manager for a controller's game-saves report."""
        dlg = cls(controller.game_saves_report(), controller, parent)
        dlg.show()
        return dlg
