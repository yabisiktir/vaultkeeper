"""FindFilesDialog — search a profile's files (VB ``FindProfileFilesDialogue``).

Type part of a file name to list every mod file that matches, with optional
match-case / whole-word filters, showing each hit's mod, file and sub-folder.
**Select** jumps the main window's mod list to the chosen file's mod (VB
``SelectMod``). Data comes from ``ProfileController.find_profile_files``.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry

_MOD_ROLE = Qt.ItemDataRole.UserRole


class FindFilesDialog(QDialog):
    """Search installer files across the profile and jump to a hit's mod."""

    def __init__(
        self,
        controller,
        on_select: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._on_select = on_select
        self.setWindowTitle("Find Files in Profile")
        geometry.remember(self, "FindFilesDialog", 560, 420)

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Find what:"))
        self._find = QLineEdit()
        self._find.setPlaceholderText("Part of a file name…")
        self._find.textChanged.connect(self._search)
        top.addWidget(self._find, 1)
        layout.addLayout(top)

        options = QHBoxLayout()
        self._whole_word = QCheckBox("Match whole word only")
        self._whole_word.toggled.connect(self._search)
        self._match_case = QCheckBox("Match case")
        self._match_case.toggled.connect(self._search)
        options.addWidget(self._whole_word)
        options.addWidget(self._match_case)
        options.addStretch(1)
        layout.addLayout(options)

        self._results = QTreeWidget()
        self._results.setHeaderLabels(["Mod Name", "File Name", "Sub-Folder"])
        self._results.setRootIsDecorated(False)
        self._results.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._results.itemDoubleClicked.connect(lambda *_: self._select())
        layout.addWidget(self._results, 1)

        self._count = QLabel("Files Found: None")
        layout.addWidget(self._count)

        bar = QHBoxLayout()
        bar.addStretch(1)
        self._select_btn = QPushButton("Select")
        self._select_btn.setEnabled(False)
        self._select_btn.clicked.connect(self._select)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        bar.addWidget(self._select_btn)
        bar.addWidget(close)
        layout.addLayout(bar)

    def _search(self, *_args) -> None:
        report = self._controller.find_profile_files(
            self._find.text(),
            match_case=self._match_case.isChecked(),
            whole_word=self._whole_word.isChecked(),
        )
        self._results.clear()
        for row in report["rows"]:
            item = QTreeWidgetItem([row["mod"], row["filename"], row["folder"]])
            item.setData(0, _MOD_ROLE, row["mod"])
            self._results.addTopLevelItem(item)
        count = report["count"]
        self._count.setText(f"Files Found: {count or 'None'}")
        if count:
            self._results.setCurrentItem(self._results.topLevelItem(0))
        self._select_btn.setEnabled(bool(count))

    def _select(self) -> None:
        item = self._results.currentItem()
        if item is None:
            return
        mod = item.data(0, _MOD_ROLE)
        if mod and self._on_select is not None:
            self._on_select(mod)

    @classmethod
    def show_for(cls, controller, on_select=None, parent=None) -> FindFilesDialog:
        dlg = cls(controller, on_select, parent)
        dlg.show()
        return dlg
