"""The start-up options menu and the pre-load data-backup list (VB MsgOptions).

Both of these run *before* the profile is loaded, which is the only reason they
are useful: they are what you get to when loading the profile is the thing that
crashes.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QRadioButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.startup_options import StartupOptions, menu_options
from vaultkeeper.ui import resources as R


class StartupOptionsDialog(QDialog):
    """Pick one start-up option (VB ``DisplayStartOptions``)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Start-up Options")
        self.setWindowIcon(R.app_icon())

        layout = QVBoxLayout(self)
        heading = QLabel("Specify a start-up option.")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)
        note = QLabel(
            "These run before Vaultkeeper loads your profile, so they still work "
            "when loading it is what goes wrong."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._buttons: list[tuple[str, QRadioButton]] = []
        for index, (name, description) in enumerate(menu_options()):
            button = QRadioButton(_spaced(name))
            button.setToolTip(description)
            button.setChecked(index == 0)
            layout.addWidget(button)
            hint = QLabel(description)
            hint.setWordWrap(True)
            hint.setContentsMargins(22, 0, 0, 6)
            hint.setEnabled(False)
            layout.addWidget(hint)
            self._buttons.append((name, button))

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.button(QDialogButtonBox.StandardButton.Ok).setText("Continue")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def chosen(self) -> str | None:
        for name, button in self._buttons:
            if button.isChecked():
                return name
        return None

    @classmethod
    def choose(
        cls, options: StartupOptions, parent: QWidget | None = None
    ) -> StartupOptions:
        """Show the menu and fold the answer in. Cancel changes nothing."""
        dialog = cls(parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return options
        name = dialog.chosen()
        return options.with_option(name) if name else options


def _spaced(name: str) -> str:
    """``RestoreProfileData`` → ``Restore Profile Data`` (VB ``ToSentence``)."""
    out = []
    for index, char in enumerate(name):
        if index and char.isupper():
            out.append(" ")
        out.append(char)
    return "".join(out)


class DataBackupDialog(QDialog):
    """Restore a profile store from a backup, before anything reads it."""

    def __init__(self, backups: list[Path], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backups = list(backups)

        self.setWindowTitle("Restore Profile Data")
        self.setWindowIcon(R.app_icon())
        self.resize(620, 360)

        layout = QVBoxLayout(self)
        heading = QLabel("Restore profile information from a backup")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)
        note = QLabel(
            "Pick a backup and click Restore. The file it replaces is kept "
            "alongside it, so restoring the wrong one is not the end of the road."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["Backup", "Saved", "Size"])
        self.table.setRootIsDecorated(False)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for path in self._backups:
            stat = path.stat()
            from datetime import datetime

            item = QTreeWidgetItem(
                [
                    path.name,
                    datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    f"{stat.st_size:,} bytes",
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            self.table.addTopLevelItem(item)
        if self._backups:
            self.table.setCurrentItem(self.table.topLevelItem(0))
        layout.addWidget(self.table, 1)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.button(QDialogButtonBox.StandardButton.Ok).setText("Restore")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("Continue Without Restoring")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def selected(self) -> Path | None:
        item = self.table.currentItem()
        if item is None:
            return None
        return Path(item.data(0, Qt.ItemDataRole.UserRole))
