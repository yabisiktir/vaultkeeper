"""Crash Dump File Manager (VB ``CrashDumpManager``).

Shown after a play session that produced new crash files (and on request): the
game's crash files, newest first, with Open Folder, Delete and Delete All. NIT's
Submit opened the folder and Beamdog's support page; the folder is opened here
(the support address comes from NIT's definitions file). Deletes go to the
recycle bin. Captions from ``CrashDumpManager.Designer.vb``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry

#: Where Beamdog takes crash reports (NIT ``Application Definitions.txt``,
#: ``BeamdogSupportPage``).
BEAMDOG_CRASH_PAGE = "https://nwn.beamdog.net/crash"


class CrashReportsDialog(QDialog):
    def __init__(self, controller, info: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Crash Dump File Manager")
        geometry.remember(self, "CrashReports", 520, 360)
        layout = QVBoxLayout(self)
        self.info = QLabel(info)
        self.info.setWordWrap(True)
        self.info.setVisible(bool(info))
        layout.addWidget(self.info)
        layout.addWidget(QLabel("Date and Time of Crash"))
        self.files = QListWidget()
        self.files.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.files, 1)

        buttons = QDialogButtonBox()
        # VB BtSubmit: show the crash file, then Beamdog's crash-report page, so
        # the file is at hand to attach.
        self.submit_button = buttons.addButton("&Submit", QDialogButtonBox.ButtonRole.ActionRole)
        self.submit_button.setToolTip(f"Show the crash file and open {BEAMDOG_CRASH_PAGE}")
        self.submit_button.clicked.connect(self._on_submit)
        self.open_button = buttons.addButton("&Open Folder", QDialogButtonBox.ButtonRole.ActionRole)
        self.delete_button = buttons.addButton("&Delete", QDialogButtonBox.ButtonRole.ActionRole)
        self.delete_all_button = buttons.addButton(
            "Delete &All", QDialogButtonBox.ButtonRole.ActionRole
        )
        buttons.addButton("&Close", QDialogButtonBox.ButtonRole.RejectRole)
        self.open_button.clicked.connect(self._on_open)
        self.delete_button.clicked.connect(self._on_delete)
        self.delete_all_button.clicked.connect(self._on_delete_all)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._reload()

    def _reload(self) -> None:
        self.files.clear()
        for crash in self._controller.crash_reports():
            item = QListWidgetItem(
                f"{crash.modified:%d %b %Y %H:%M:%S}    {crash.path.name}"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(crash.path))
            self.files.addItem(item)
        if self.files.count():
            self.files.setCurrentRow(0)
        has = self.files.count() > 0
        for button in (
            self.submit_button, self.open_button, self.delete_button, self.delete_all_button
        ):
            button.setEnabled(has)

    def _paths(self, items) -> list[str]:
        return [i.data(Qt.ItemDataRole.UserRole) for i in items]

    def _on_submit(self) -> None:
        self._on_open()
        QDesktopServices.openUrl(QUrl(BEAMDOG_CRASH_PAGE))

    def _on_open(self) -> None:
        item = self.files.currentItem() or self.files.item(0)
        if item is not None:
            from pathlib import Path

            folder = Path(item.data(Qt.ItemDataRole.UserRole)).parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_delete(self) -> None:
        self._controller.delete_crash_reports(self._paths(self.files.selectedItems()))
        self._reload()

    def _on_delete_all(self) -> None:
        items = [self.files.item(i) for i in range(self.files.count())]
        self._controller.delete_crash_reports(self._paths(items))
        self._reload()
