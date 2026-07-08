"""WorkshopViewer — Steam Workshop subscriptions (VB ``WorkshopViewer``).

Lists the Steam Workshop item folders NIT can see, whether each is *managed* by a
mod, and the mod it maps to; selecting an item shows that folder's contents.
Built on ``ProfileController.workshop_report`` / ``workshop_item_files``.

Read-only. The VB Refresh re-scans Steam's folders (here it just rebuilds from disk)
and the "Copy MapId Rule" context action are a thin layer over the same report.
The persistent WorkshopContents database, network title fetch and name editor are
deferred (see the SteamWorkshop domain slice).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R


class WorkshopViewer(QDialog):
    """A read-only table of Steam Workshop subscriptions + folder contents."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Steam Workshop Subscriptions")
        self.setWindowIcon(R.get_icon("SteamViewer"))
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        self.header = QLabel()
        self.header.setWordWrap(True)
        layout.addWidget(self.header)

        splitter = QSplitter()
        layout.addWidget(splitter, 1)

        self.items = QTreeWidget()
        self.items.setHeaderLabels(["Workshop Id", "Managed", "Mod Name"])
        self.items.setRootIsDecorated(False)
        self.items.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.items.currentItemChanged.connect(self._on_selection)
        splitter.addWidget(self.items)

        self.contents = QTreeWidget()
        self.contents.setHeaderLabels(["Subscription Contents", "Size"])
        self.contents.setRootIsDecorated(False)
        splitter.addWidget(self.contents)
        splitter.setSizes([440, 320])

        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.refresh()

    def refresh(self) -> None:
        """(Re)build the subscription list from disk (VB ``BtRefresh``)."""
        report = self._controller.workshop_report()
        self._rows = report["rows"]
        path = report["content_path"] or "not configured"
        self.header.setText(
            f"View information about your Steam Workshop Subscriptions\n{path}"
        )
        self.summary.setText(report["summary"])

        self.items.clear()
        for row in self._rows:
            self.items.addTopLevelItem(
                QTreeWidgetItem([row["id"], row["managed"], row["mod"]])
            )
        if self.items.topLevelItemCount() > 0:
            self.items.setCurrentItem(self.items.topLevelItem(0))
        else:
            self.contents.clear()

    def _on_selection(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        self.contents.clear()
        if current is None:
            return
        row = self._rows[self.items.indexOfTopLevelItem(current)]
        for entry in self._controller.workshop_item_files(row["folder"]):
            self.contents.addTopLevelItem(
                QTreeWidgetItem([entry["name"], entry["size"]])
            )

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> WorkshopViewer:
        """Build and show the viewer for a controller's workshop report."""
        dlg = cls(controller, parent)
        dlg.show()
        return dlg
