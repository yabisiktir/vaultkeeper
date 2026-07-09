"""FolderMapping — view *and edit* the Mapper's folder-mapping rules (VB Settings map pages).

Three tabs mirror the VB Settings list-views: **Extensions** (``LvMapExtensions``:
Extension / Default Folder / Secondary Folder), **Map Files** (``LvMapFiles``: File
Name / NWN Folder) and **Map Folders** (``LvMapFolders``: Source Folder / NWN Folder).
Built on ``ProfileController.folder_mapping_report`` and the map-edit methods.

Editing surface: an *Add / Update* row (key + NWN folder) applies a user override to
the current tab's table, *Remove Selected* deletes a user override (built-in defaults
are not removable — a persisted deletion of a default is deferred), and *Reset All*
restores the default tables. Overrides are shown in bold and persist to the settings
file. The VB per-list rename-in-place editor, import-from-game and secondary-folder
editing are deferred with the rest of the Settings subsystem. Column captions come
from ``Settings.Designer.vb``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R

#: Tab-name -> index, so callers/tests can request a start page by name.
TAB_INDEX = {"Extensions": 0, "Map Files": 1, "Map Folders": 2, "Map Excludes": 3}

#: The Excludes tab index (edit shape differs: name + File/Folder type).
_EXCLUDES_TAB = 3

#: Per-map-tab (override-table name, key-column label) used by the edit controls.
_TAB_TABLES = [
    ("ext_mapping", "Extension"),
    ("exception_files", "File Name"),
    ("dir_mapping", "Source Folder"),
]

#: Common NWN target folders offered in the folder combo (editable — any name allowed).
_FOLDER_CHOICES = [
    "override", "hak", "tlk", "modules", "nwm", "ambient", "music", "movies",
    "portraits", "localvault", "dmvault", "patch", "database", "erf",
    "texturepacks", "nwn",
]


class FolderMapping(QDialog):
    """A tabbed view + editor of the Mapper's folder-mapping tables."""

    def __init__(
        self, controller, start_tab: str = "Extensions", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Folder Mapping")
        self.setWindowIcon(R.get_icon("MapToFolder_32x"))
        self.resize(600, 600)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.extensions = self._make_tab(
            ["Extension", "Default Folder", "Secondary Folder"]
        )
        self.files = self._make_tab(["File Name", "NWN Folder"])
        self.folders = self._make_tab(["Source Folder", "NWN Folder"])
        self.excludes = self._make_tab(["Excluded Item", "Type"])
        self.tabs.addTab(self.extensions, "Extensions")
        self.tabs.addTab(self.files, "Map Files")
        self.tabs.addTab(self.folders, "Map Folders")
        self.tabs.addTab(self.excludes, "Map Excludes")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        for tree in (self.extensions, self.files, self.folders, self.excludes):
            tree.itemSelectionChanged.connect(self._update_buttons)

        # -- Edit row ------------------------------------------------------- #
        edit_row = QHBoxLayout()
        self._key_label = QLabel("Extension:")
        self._key_edit = QLineEdit()
        self._folder_combo = QComboBox()
        self._folder_combo.setEditable(True)
        self._folder_combo.addItems(_FOLDER_CHOICES)
        self._add_button = QPushButton("Add / Update")
        self._add_button.clicked.connect(self._on_add)
        self._remove_button = QPushButton("Remove Selected")
        self._remove_button.clicked.connect(self._on_remove)
        edit_row.addWidget(self._key_label)
        edit_row.addWidget(self._key_edit, 1)
        edit_row.addWidget(QLabel("→"))
        edit_row.addWidget(self._folder_combo, 1)
        edit_row.addWidget(self._add_button)
        edit_row.addWidget(self._remove_button)
        layout.addLayout(edit_row)

        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        self._reset_button = QPushButton("Reset All to Defaults")
        self._reset_button.clicked.connect(self._on_reset)
        buttons.addWidget(self._reset_button)
        buttons.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.refresh()
        self.tabs.setCurrentIndex(TAB_INDEX.get(start_tab, 0))
        self._on_tab_changed(self.tabs.currentIndex())

    @staticmethod
    def _make_tab(headers: list[str]) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(headers)
        tree.setRootIsDecorated(False)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return tree

    # -- Population -------------------------------------------------------- #
    def refresh(self) -> None:
        """(Re)build every table from the reports."""
        report = self._controller.folder_mapping_report()
        excludes = self._controller.map_excludes_report()
        self.summary.setText(f"{report['summary']} {excludes['summary']}")
        self._fill(
            self.extensions,
            [
                (r["ext"], (r["ext"], r["folder"], r["secondary"]), r["override"])
                for r in report["extensions"]
            ],
        )
        self._fill(
            self.files,
            [(r["file"], (r["file"], r["folder"]), r["override"]) for r in report["files"]],
        )
        self._fill(
            self.folders,
            [
                (r["source"], (r["source"], r["folder"]), r["override"])
                for r in report["folders"]
            ],
        )
        self._fill(
            self.excludes,
            [(r["name"], (r["name"], "File"), r["override"]) for r in excludes["files"]]
            + [
                (r["name"], (r["name"], "Folder"), r["override"])
                for r in excludes["folders"]
            ],
        )
        self._update_buttons()

    @staticmethod
    def _fill(tree: QTreeWidget, rows: list[tuple[str, tuple[str, ...], bool]]) -> None:
        tree.clear()
        for key, columns, is_override in rows:
            item = QTreeWidgetItem(list(columns))
            item.setData(0, Qt.ItemDataRole.UserRole, (key, is_override))
            if is_override:
                font = item.font(0)
                font.setWeight(QFont.Weight.Bold)
                for col in range(len(columns)):
                    item.setFont(col, font)
            tree.addTopLevelItem(item)

    # -- Edit controls ----------------------------------------------------- #
    def _current_tree(self) -> QTreeWidget:
        return (self.extensions, self.files, self.folders, self.excludes)[
            self.tabs.currentIndex()
        ]

    def _on_tab_changed(self, index: int) -> None:
        self._key_edit.clear()
        self._folder_combo.clear()
        if index == _EXCLUDES_TAB:
            self._key_label.setText("Excluded Item:")
            self._folder_combo.addItems(["File", "Folder"])
        else:
            self._key_label.setText(f"{_TAB_TABLES[index][1]}:")
            self._folder_combo.addItems(_FOLDER_CHOICES)
        self._update_buttons()

    def _update_buttons(self) -> None:
        item = self._current_tree().currentItem()
        is_override = bool(item and item.data(0, Qt.ItemDataRole.UserRole)[1])
        self._remove_button.setEnabled(is_override)

    def _on_add(self) -> None:
        key = self._key_edit.text().strip()
        choice = self._folder_combo.currentText().strip()
        if not key or not choice:
            return
        index = self.tabs.currentIndex()
        if index == 0:
            self._controller.set_map_extension(key, choice)
        elif index == 1:
            self._controller.set_map_file_exception(key, choice)
        elif index == 2:
            self._controller.set_map_folder(key, choice)
        else:
            self._controller.add_map_exclude(
                "files" if choice == "File" else "folders", key
            )
        self._key_edit.clear()
        self.refresh()

    def _on_remove(self) -> None:
        item = self._current_tree().currentItem()
        if item is None:
            return
        key, is_override = item.data(0, Qt.ItemDataRole.UserRole)
        if not is_override:
            return
        index = self.tabs.currentIndex()
        if index == _EXCLUDES_TAB:
            kind = "files" if item.text(1) == "File" else "folders"
            self._controller.remove_map_exclude(kind, key)
        else:
            self._controller.remove_map_override(_TAB_TABLES[index][0], key)
        self.refresh()

    def _on_reset(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Reset Folder Mapping",
            "Discard all your map customisations and restore the defaults?",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._controller.reset_map_overrides()
            self.refresh()

    @classmethod
    def show_for(
        cls,
        controller,
        start_tab: str = "Extensions",
        parent: QWidget | None = None,
    ) -> FolderMapping:
        """Build and show the folder-mapping view, optionally on a start tab."""
        dlg = cls(controller, start_tab, parent)
        dlg.show()
        return dlg
