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

from vaultkeeper.ui import geometry
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
        geometry.remember(self, "GameSavesManager", 640, 520)

        layout = QVBoxLayout(self)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Folder", "Save Name", "Location", "Type", "Size"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.currentItemChanged.connect(lambda *_: self._sync_buttons())
        # openagamesavefolderwithwindowsfi.htm names four ways to do this —
        # "click the Open with File Explorer icon, double-click the folder,
        # press Ctrl+O or right-click the folder" — and only the icon existed.
        # newtopic60.htm asks for Character Summary on the same right-click.
        self.table.itemDoubleClicked.connect(lambda *_a: self._on_open_folder())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_save_menu)
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
        # "You should delete the Game Saves when you have completed playing a Mod
        # so that the Installer Tool can record how long you spent playing the
        # Mod" (deletinggamesaves.htm). Deleting them one at a time gets there
        # eventually; this is the button that says what you mean.
        self.finished_button = QPushButton("Finished")
        self.finished_button.setIcon(R.get_icon("StatusOK_16x"))
        self.finished_button.setToolTip(
            "Delete every save for this game and record how long it was played"
        )
        self.finished_button.clicked.connect(self._on_finished)
        self.reduce_button = QPushButton("Reduce")
        self.reduce_button.clicked.connect(self._on_reduce)
        reduce_row.addWidget(self.summary_button)
        reduce_row.addWidget(self.open_button)
        reduce_row.addWidget(self.finished_button)
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
        # The mirror of Activate's right-click: put the saves away and take the
        # mod out with them (startanewgame.htm).
        self.deactivate_button.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.deactivate_button.customContextMenuRequested.connect(
            lambda _pos: self._on_deactivate(with_mods=True)
        )
        self.deactivate_button.setToolTip(
            "Move the current game's saves to a backup.\n"
            "Right-click to uninstall its mod as well."
        )
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

        # VB reports the auto-backup on the manager's own status line, not in a
        # message box: it is something that has already happened, not a question.
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        button_row = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        button_row.addWidget(help_button("BhGameManager", self))
        button_row.addStretch(1)
        self.restore_button = QPushButton("Restore")
        self.restore_button.clicked.connect(self._on_restore)
        button_row.addWidget(self.restore_button)
        # deletearchives.htm: an archived range can be thrown away as well as
        # brought back. Without this, Reduce was a one-way door — saves you
        # archived to get them out of the way could only ever come back.
        self.delete_archive_button = QPushButton("Delete Archive")
        self.delete_archive_button.clicked.connect(self._on_delete_archive)
        button_row.addWidget(self.delete_archive_button)
        self.activate_button = QPushButton("Activate")
        self.activate_button.clicked.connect(self._on_activate)
        # Right-click activates *and* swaps the mods over — a game save is no use
        # without the mod that wrote it, and switching between two mods'
        # campaigns otherwise means doing the install by hand afterwards
        # (restoregamesavesfrombackup.htm, switchinggamesaves.htm).
        self.activate_button.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.activate_button.customContextMenuRequested.connect(
            lambda _pos: self._on_activate(with_mods=True)
        )
        self.activate_button.setToolTip(
            "Activate the selected game saves.\n"
            "Right-click to install its mod (and uninstall the current one) too."
        )
        button_row.addWidget(self.activate_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._on_delete)
        button_row.addWidget(self.delete_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._install_shortcuts()
        self._populate(report)

    def _install_shortcuts(self) -> None:
        """The manager's own keys (``keyboardshortcuts.htm``).

        The topic gives this dialog a shortcut table of its own — Ctrl+A
        Activate, Ctrl+D Deactivate, Ctrl+Minus Reduce, Ctrl+Plus Restore — and
        none of them existed. They are window-scoped *to this dialog*, so the
        main window's Ctrl+A (Select All) is untouched while it is open, and
        none of these keys mean anything to a text field.

        A shortcut whose button is disabled does nothing, rather than acting on
        a selection that is not there.
        """
        from PySide6.QtGui import QKeySequence, QShortcut

        for keys, button in (
            ("Ctrl+A", lambda: self.activate_button),
            ("Ctrl+D", lambda: self.deactivate_button),
            ("Ctrl+-", lambda: self.reduce_button),
            ("Ctrl++", lambda: self.restore_button),
        ):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(
                lambda b=button: b().isEnabled() and b().click()
            )

        # openagamesavefolderwithwindowsfi.htm names Ctrl+O as one of its four
        # ways to open the selected folder. Scoped to the save table so it only
        # fires with a save row in hand.
        open_shortcut = QShortcut(QKeySequence("Ctrl+O"), self.table)
        open_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        open_shortcut.activated.connect(self._on_open_folder)

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

    def _show_save_menu(self, pos) -> None:
        """Right-click a save row (openagamesavefolderwithwindowsfi / newtopic60).

        Both topics describe reaching these two actions by right-clicking the
        folder — "Open with File Explorer" and "Display Character Summary" — and
        the table had no menu at all. The buttons below are the same actions;
        this is the third documented way in, and the one those two topics name.
        """
        from PySide6.QtGui import QKeySequence
        from PySide6.QtWidgets import QMenu

        if self._selected_save() is None:
            return
        menu = QMenu(self)
        open_action = menu.addAction("Open with File Explorer", self._on_open_folder)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        menu.addAction("Display Character Summary", self._on_character_summary)
        # popup(), not exec(): exec() opens a nested event loop that a headless
        # test cannot escape, and QMenu.exec cannot be patched in PySide6.
        menu.popup(self.table.viewport().mapToGlobal(pos))

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
        has_archive = bool(self._controller) and self.archives.currentItem() is not None
        self.restore_button.setEnabled(has_archive)
        self.delete_archive_button.setEnabled(has_archive)
        has_game = bool(self._controller) and self.games.currentItem() is not None
        self.activate_button.setEnabled(has_game)
        self.delete_button.setEnabled(has_game)
        # Both act on the selected *save*, so they follow that table, not these.
        has_save = bool(self._controller) and self.table.currentItem() is not None
        self.summary_button.setEnabled(has_save)
        self.open_button.setEnabled(has_save)
        self.finished_button.setEnabled(has_save)

    def set_status(self, text: str) -> None:
        """Show a line about something the manager did on the way in."""
        self.status.setText(text)

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

    def _on_delete_archive(self) -> None:
        """Throw an archived range away (``deletearchives.htm``)."""
        item = self.archives.currentItem()
        if self._controller is None or item is None:
            return
        range_name = item.text(0)
        # The prompt says where they are going, because that decides whether
        # this can be undone (restoringdeletedsavesfromtherecy.htm).
        recycle = self._controller._settings().recycle_game_saves
        where = (
            "They can be restored from the recycle bin."
            if recycle
            else "This cannot be undone — your Recycle Bin for Game Saves "
            "preference is off."
        )
        if (
            QMessageBox.question(
                self,
                "Delete Archived Game Saves",
                f"Delete the archived game saves in {range_name}?\n\n{where}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.delete_archived_saves(range_name)
        self._refresh()
        self._report(result["message"], result["ok"])

    def _on_deactivate(self, *, with_mods: bool = False) -> None:
        if self._controller is None:
            return
        # Asked before the saves move: afterwards there is nothing left to say
        # which mod they belonged to.
        game = self._controller.current_game_name() if with_mods else ""
        question = "Move the current game's saves to a backup?"
        if with_mods:
            question += "\n\nIts mod will be uninstalled as well."
        if (
            QMessageBox.question(self, "Deactivate Game", question)
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.deactivate_current_game()
        if with_mods and result["ok"] and game:
            removed = self._controller.uninstall_game_mod(game)
            result = {
                "ok": result["ok"] and removed["ok"],
                "message": f"{result['message']} {removed['message']}",
            }
        self._refresh()
        self._report(result["message"], result["ok"])

    def _on_activate(self, *, with_mods: bool = False) -> None:
        item = self.games.currentItem()
        if self._controller is None or item is None:
            return
        name = item.text(0)
        question = f"Activate {name}? The current game will be backed up first."
        if with_mods:
            question += (
                "\n\nIts mod will be installed as well, and the mod belonging to "
                "the current saves uninstalled."
            )
        if (
            QMessageBox.question(self, "Activate Game", question)
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.activate_game(name)
        if with_mods and result["ok"]:
            swap = self._controller.swap_game_mods(name)
            result = {
                "ok": result["ok"] and swap["ok"],
                "message": f"{result['message']} {swap['message']}",
            }
        self._refresh()
        self._report(result["message"], result["ok"])

    def _on_delete(self) -> None:
        item = self.games.currentItem()
        if self._controller is None or item is None:
            return
        name = item.text(0)
        recycle = self._controller._settings().recycle_game_saves
        where = (
            "It can be restored from the recycle bin."
            if recycle
            else "This cannot be undone — your Recycle Bin for Game Saves "
            "preference is off."
        )
        if (
            QMessageBox.question(
                self,
                "Delete Game Backup",
                f"Delete the backup for {name}?\n\n{where}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.delete_game_backup(name)
        self._refresh()
        self._report(result["message"], result["ok"])

    def _on_finished(self) -> None:
        """Delete every save for the selected game and record the play time."""
        row = self._selected_save()
        if row is None or self._controller is None:
            return
        save_name = row.get("save") or ""
        if not save_name:
            return
        if (
            QMessageBox.question(
                self,
                "Finished",
                f"Finish '{save_name}'?\n\n"
                "Its game saves are moved to the archive (restorable from this "
                "window) and its play time is recorded — that is what tells the "
                "tool the game is over rather than paused.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.finish_game(save_name)
        self._refresh()
        self._report(result["message"], result["ok"])

    def _report(self, message: str, ok: bool) -> None:
        if ok:
            QMessageBox.information(self, "Game Saves Manager", message)
        else:
            QMessageBox.warning(self, "Game Saves Manager", message)

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> GameSavesManager:
        """Build and show the manager for a controller's game-saves report.

        Opening it is also when other mods' saves are moved aside (VB
        ``SanitiseGameSaves``, from ``PopulateSaveList``) — so the report is
        taken *after* that, or it would describe a folder that no longer exists.
        """
        auto = controller.auto_backup_other_games()
        report = controller.game_saves_report()
        report["backup"] = controller.deactivated_games_report()
        dlg = cls(report, controller, parent)
        if auto.get("message"):
            dlg.set_status(auto["message"])
        dlg.show()
        return dlg
