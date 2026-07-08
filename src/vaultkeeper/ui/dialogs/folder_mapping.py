"""FolderMapping — view the Mapper's folder-mapping rules (VB Settings map pages).

Read-only view of the rules that decide where each mod file installs, drawn from
``core/mapper.py`` (the tested v21 default tables). Three tabs mirror the VB Settings
list-views: **Extensions** (``LvMapExtensions``: Extension / Default Folder / Secondary
Folder), **Map Files** (``LvMapFiles``: File Name / NWN Folder) and **Map Folders**
(``LvMapFolders``: Source Folder / NWN Folder). Built on
``ProfileController.folder_mapping_report``.

The VB ribbon buttons open the Settings dialog on a start page: *Map Files*
(``RbnMapFiles``) and *Map Folders* (``RbnMapFolders``); ``show_for`` accepts a
``start_tab`` to match. The editing surface (add/rename/reset/import, persistence)
is deferred with the rest of the Settings subsystem — see the handoff. Column
captions come from ``Settings.Designer.vb``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R

#: Tab-name -> index, so callers/tests can request a start page by name.
TAB_INDEX = {"Extensions": 0, "Map Files": 1, "Map Folders": 2}


class FolderMapping(QDialog):
    """A read-only tabbed view of the Mapper's folder-mapping tables."""

    def __init__(
        self, controller, start_tab: str = "Extensions", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Folder Mapping")
        self.setWindowIcon(R.get_icon("MapToFolder_32x"))
        self.resize(560, 560)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.extensions = self._make_tab(
            ["Extension", "Default Folder", "Secondary Folder"]
        )
        self.files = self._make_tab(["File Name", "NWN Folder"])
        self.folders = self._make_tab(["Source Folder", "NWN Folder"])
        self.tabs.addTab(self.extensions, "Extensions")
        self.tabs.addTab(self.files, "Map Files")
        self.tabs.addTab(self.folders, "Map Folders")

        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.refresh()
        self.tabs.setCurrentIndex(TAB_INDEX.get(start_tab, 0))

    @staticmethod
    def _make_tab(headers: list[str]) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(headers)
        tree.setRootIsDecorated(False)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        return tree

    def refresh(self) -> None:
        """(Re)build all three tables from the report."""
        report = self._controller.folder_mapping_report()
        self.summary.setText(report["summary"])
        self._fill(
            self.extensions,
            [(r["ext"], r["folder"], r["secondary"]) for r in report["extensions"]],
        )
        self._fill(self.files, [(r["file"], r["folder"]) for r in report["files"]])
        self._fill(
            self.folders, [(r["source"], r["folder"]) for r in report["folders"]]
        )

    @staticmethod
    def _fill(tree: QTreeWidget, rows: list[tuple[str, ...]]) -> None:
        tree.clear()
        for row in rows:
            tree.addTopLevelItem(QTreeWidgetItem(list(row)))

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
