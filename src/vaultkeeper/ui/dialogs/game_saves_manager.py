"""GameSavesManager — the game-saves listing + archive dialog (VB ``GameManager``).

Lists the current NWN game saves (folder, save name, in-module location, save type,
size) with a summary line, plus the current game's archived save ranges. Offers the
**Reduce** action (archive the oldest saves, keeping the newest N — VB ``NudKeep`` /
``ArchiveGames``) and **Restore** (bring an archived range back — VB ``RestoreGames``),
driven through ``ProfileController``.

The two-list layout mirrors the VB manager: the current game's saves on top, a second
list of **deactivated games** (backups) below, with **Deactivate** (move the active
game to a backup — VB ``DeactivateGame``), **Activate** (restore a backup, backing up
the current game first — VB ``ActivateGame``) and **Delete** (remove a backup — VB
``DeleteGame``), plus the Backups space total.

Bounded: the three-way "already archived" prompt is not surfaced — a Reduce onto an
existing range merges into it (``on_existing="overwrite"``).
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
        self.table.currentItemChanged.connect(lambda *_: self._sync_buttons())
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
        self.summary_button = QPushButton("Character Summary")
        self.summary_button.setIcon(R.get_icon("LookupUser_16x"))
        self.summary_button.setToolTip("Show the character in the selected save")
        self.summary_button.clicked.connect(self._on_character_summary)
        self.open_button = QPushButton("Open Folder")
        self.open_button.setIcon(R.get_icon("Mod Explorer 1"))
        self.open_button.setToolTip("Open the selected save's folder")
        self.open_button.clicked.connect(self._on_open_folder)
        self.reduce_button = QPushButton("Reduce")
        self.reduce_button.clicked.connect(self._on_reduce)
        reduce_row.addWidget(self.summary_button)
        reduce_row.addWidget(self.open_button)
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

        # -- Deactivated games (backups) + Activate/Delete -------------------- #
        games_header = QHBoxLayout()
        games_header.addWidget(QLabel("Deactivated games (backups)"))
        games_header.addStretch(1)
        self.deactivate_button = QPushButton("Deactivate Current Game")
        self.deactivate_button.clicked.connect(self._on_deactivate)
        games_header.addWidget(self.deactivate_button)
        layout.addLayout(games_header)

        self.games = QTreeWidget()
        self.games.setHeaderLabels(["Game", "Saves", "Size"])
        self.games.setRootIsDecorated(False)
        self.games.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.games.itemSelectionChanged.connect(self._sync_buttons)
        layout.addWidget(self.games)

        self.backup_total = QLabel()
        layout.addWidget(self.backup_total)

        button_row = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        button_row.addWidget(help_button("BhGameManager", self))
        button_row.addStretch(1)
        self.restore_button = QPushButton("Restore")
        self.restore_button.clicked.connect(self._on_restore)
        button_row.addWidget(self.restore_button)
        self.activate_button = QPushButton("Activate")
        self.activate_button.clicked.connect(self._on_activate)
        button_row.addWidget(self.activate_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._on_delete)
        button_row.addWidget(self.delete_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._populate(report)

    # -- Rendering -------------------------------------------------------- #
    # -- Row actions (VB CmCharacterSummary / CmOpen) ---------------------- #
    def _selected_save(self) -> dict | None:
        item = self.table.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def _on_character_summary(self) -> None:
        """Show the character stored in the selected save (VB CmCharacterSummary)."""
        row = self._selected_save()
        if row is None or self._controller is None:
            return
        from pathlib import Path as _Path

        from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer

        folder = _Path(row.get("path", ""))
        characters = self._controller.character_files(save_folder=folder)
        if not characters:
            QMessageBox.information(
                self,
                "Character Summary",
                f"No character file was found in {row['name']}.",
            )
            return
        self._character_viewer = CharacterViewer(
            characters,
            lambda resref, own: self._controller.portrait_path(resref, extra_dirs=[own]),
            self,
        )
        self._character_viewer.show()

    def _on_open_folder(self) -> None:
        """Reveal the selected save's folder (VB CmOpen — "Open with File Explorer")."""
        from pathlib import Path as _Path

        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        row = self._selected_save()
        if row is None:
            return
        folder = _Path(row.get("path", ""))
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _populate(self, report: dict) -> None:
        self.table.clear()
        for row in report.get("rows", []):
            item = QTreeWidgetItem(
                [row["name"], row["save"], row["location"], row["type"], row["size"]]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, row)
            self.table.addTopLevelItem(item)

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
        # Second list: deactivated games (backups) + Backups space total.
        self.games.clear()
        backup = report.get("backup", {})
        for row in backup.get("games", []):
            self.games.addTopLevelItem(
                QTreeWidgetItem([row["name"], f"{row['count']:,}", row["size"]])
            )
        self.backup_total.setText(
            f"Backups total size: {backup.get('backup_total') or '0 B'}"
        )
        has_active = bool(self._controller) and count > 0
        self.deactivate_button.setEnabled(has_active)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        self.restore_button.setEnabled(
            bool(self._controller) and self.archives.currentItem() is not None
        )
        has_game = bool(self._controller) and self.games.currentItem() is not None
        self.activate_button.setEnabled(has_game)
        self.delete_button.setEnabled(has_game)
        # Both act on the selected *save*, so they follow that table, not these.
        has_save = bool(self._controller) and self.table.currentItem() is not None
        self.summary_button.setEnabled(has_save)
        self.open_button.setEnabled(has_save)

    def _refresh(self) -> None:
        if self._controller is not None:
            report = self._controller.game_saves_report()
            report["backup"] = self._controller.deactivated_games_report()
            self._populate(report)

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

    def _on_deactivate(self) -> None:
        if self._controller is None:
            return
        if (
            QMessageBox.question(
                self,
                "Deactivate Game",
                "Move the current game's saves to a backup?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.deactivate_current_game()
        self._refresh()
        self._report(result["message"], result["ok"])

    def _on_activate(self) -> None:
        item = self.games.currentItem()
        if self._controller is None or item is None:
            return
        name = item.text(0)
        if (
            QMessageBox.question(
                self,
                "Activate Game",
                f"Activate {name}? The current game will be backed up first.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.activate_game(name)
        self._refresh()
        self._report(result["message"], result["ok"])

    def _on_delete(self) -> None:
        item = self.games.currentItem()
        if self._controller is None or item is None:
            return
        name = item.text(0)
        if (
            QMessageBox.question(
                self,
                "Delete Game Backup",
                f"Permanently delete the backup for {name}?",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.delete_game_backup(name)
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
        report = controller.game_saves_report()
        report["backup"] = controller.deactivated_games_report()
        dlg = cls(report, controller, parent)
        dlg.show()
        return dlg
