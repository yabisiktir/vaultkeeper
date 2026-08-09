"""BackupManager — what has been backed up and exported (VB ``BackupManager``).

Three tabs, because the three are restored by three different routes and
deleting from one says nothing about the others: **Data Backups** (the copies
taken before a destructive operation, plus whatever Backup Data has written),
**Exported Settings** and **Exported Mods**.

Restore is offered only for a profile-store backup, which is the one thing here
that can be put back without asking anything further. The archives from Backup
Data go through *Restore Data* on the File menu, which knows how to unpack them.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.dialogs.help_viewer import help_button

#: Tab title → the report key it lists.
_TABS = (
    ("Data Backups", "data_backups"),
    ("Exported Settings", "exported_settings"),
    ("Exported Mods", "exported_mods"),
)

_PATH_ROLE = Qt.ItemDataRole.UserRole


def _size(byte_count: int) -> str:
    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} GB"


class BackupManager(QDialog):
    """List, restore and delete backups and exports."""

    def __init__(self, report: dict, controller=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller

        self.setWindowTitle("Backup and Export Manager")
        self.setWindowIcon(R.get_icon("DataCompare_16x"))
        geometry.remember(self, "BackupManager", 700, 460)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tables: dict[str, QTreeWidget] = {}
        self.folders: dict[str, QLabel] = {}
        for title, key in _TABS:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            table = QTreeWidget()
            table.setHeaderLabels(["Name", "Saved", "Size"])
            table.setRootIsDecorated(False)
            table.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            table.itemSelectionChanged.connect(self._sync_buttons)
            page_layout.addWidget(table)
            where = QLabel("")
            where.setWordWrap(True)
            where.setEnabled(False)
            page_layout.addWidget(where)
            self.tables[key] = table
            self.folders[key] = where
            self.tabs.addTab(page, title)
        self.tabs.currentChanged.connect(lambda _i: self._sync_buttons())
        layout.addWidget(self.tabs, 1)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addWidget(help_button("BhBackupManager", self))
        self.restore_button = QPushButton("Restore")
        self.restore_button.setToolTip(
            "Put a profile-store backup back. Data Backup archives are restored "
            "with Restore Data on the File menu."
        )
        self.restore_button.clicked.connect(self._on_restore)
        buttons.addWidget(self.restore_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._on_delete)
        buttons.addWidget(self.delete_button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._populate(report)

    # -- Contents ---------------------------------------------------------- #
    def _populate(self, report: dict) -> None:
        total = 0
        for _title, key in _TABS:
            table = self.tables[key]
            table.clear()
            rows = report.get(key, [])
            total += len(rows)
            for row in rows:
                item = QTreeWidgetItem(
                    [
                        row["name"],
                        datetime.fromtimestamp(row["modified"]).strftime("%Y-%m-%d %H:%M"),
                        _size(row["size"]),
                    ]
                )
                item.setData(0, _PATH_ROLE, row["path"])
                table.addTopLevelItem(item)
            folder = (report.get("folders") or {}).get(key, "")
            self.folders[key].setText(
                f"{len(rows):,} item(s) in {folder}" if folder else ""
            )
        self.summary.setText(
            "Nothing has been backed up or exported yet."
            if not total
            else f"{total:,} backup(s) and export(s)."
        )
        self._sync_buttons()

    def _current_key(self) -> str:
        return _TABS[self.tabs.currentIndex()][1]

    def _selected(self) -> list[str]:
        table = self.tables[self._current_key()]
        return [item.data(0, _PATH_ROLE) for item in table.selectedItems()]

    def _sync_buttons(self) -> None:
        selected = self._selected()
        self.delete_button.setEnabled(bool(selected) and self._controller is not None)
        # Only a profile-store backup can be put back from here; an archive
        # needs unpacking, which is what Restore Data is for.
        restorable = (
            self._current_key() == "data_backups"
            and len(selected) == 1
            and selected[0].lower().endswith(".json")
        )
        self.restore_button.setEnabled(restorable and self._controller is not None)

    # -- Actions ----------------------------------------------------------- #
    def _on_restore(self) -> None:
        selected = self._selected()
        if self._controller is None or len(selected) != 1:
            return
        name = Path(selected[0]).name
        if (
            QMessageBox.question(
                self,
                "Restore Profile Data",
                f"Restore profile information from {name}?\n\nThe file it "
                "replaces is kept alongside it, so this is reversible.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        message = self._controller.restore_profile_backup(selected[0])
        QMessageBox.information(self, "Restore Profile Data", message)
        self.summary.setText(message)
        self._populate(self._controller.backup_manager_report())

    def _on_delete(self) -> None:
        selected = self._selected()
        if self._controller is None or not selected:
            return
        if (
            QMessageBox.question(
                self,
                "Delete",
                f"Delete {len(selected)} selected item(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        result = self._controller.delete_backup_files(selected)
        self._populate(self._controller.backup_manager_report())
        self.summary.setText(result["message"])

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> BackupManager:
        dlg = cls(controller.backup_manager_report(), controller, parent)
        dlg.show()
        return dlg
