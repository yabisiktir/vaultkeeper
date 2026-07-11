"""WorkshopViewer — Steam Workshop subscriptions (VB ``WorkshopViewer``).

Lists the Steam Workshop item folders NIT can see, whether each is *managed* by a
mod, and the mod it maps to; selecting an item shows that folder's contents.
Built on ``ProfileController.workshop_report`` / ``workshop_item_files``.

**Refresh** runs the real diff (VB ``ValidateSteamContent``): it compares Steam's
folders against the persisted ``WorkshopContents`` database and reports newly-added
subscriptions, subscriptions whose files changed, and unsubscribed items, persisting
the updated database. **Rename** edits a subscription's stored mod name (VB
``RenameMod``). The network title fetch and the "Copy MapId Rule" action are deferred.
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
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhWorkshop", self))
        buttons.addStretch(1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._on_refresh)
        self.add_button = QPushButton("Add as Mod")
        self.add_button.setToolTip("Add the selected subscription as a NIT-managed mod.")
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self._on_add)
        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self._on_rename)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._scan()

    def _on_refresh(self) -> None:
        """Diff Steam's content against the stored database (VB ``ValidateSteamContent``)."""
        diff = self._controller.workshop_refresh()
        self._scan()
        self.summary.setText(diff["summary"])

    def _on_add(self) -> None:
        """Add the selected (unmanaged) subscription as a NIT-managed mod."""
        current = self.items.currentItem()
        if current is None:
            return
        from PySide6.QtWidgets import QMessageBox

        workshop_id = current.text(0)
        confirm = QMessageBox.question(
            self,
            "Add Workshop Mod",
            f"Add Steam Workshop subscription {workshop_id} as a managed mod?\n"
            "Its content will be archived and an installer created.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        result = self._controller.add_workshop_mod(workshop_id)
        self._scan()
        QMessageBox.information(self, "Add Workshop Mod", result["message"])

    def _on_rename(self) -> None:
        """Rename the selected subscription's stored mod name (VB ``RenameMod``)."""
        current = self.items.currentItem()
        if current is None:
            return
        from PySide6.QtWidgets import QInputDialog

        workshop_id = current.text(0)
        new, ok = QInputDialog.getText(
            self, "Rename Workshop Mod", "New mod name:", text=current.text(2)
        )
        if ok and new:
            self._controller.rename_workshop_mod(workshop_id, new)
            self._scan()

    def refresh(self) -> None:
        """(Re)build the subscription list from disk (VB ``BtRefresh``)."""
        self._scan()

    def _scan(self) -> None:
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
            self.add_button.setEnabled(False)
            return
        row = self._rows[self.items.indexOfTopLevelItem(current)]
        # Only unmanaged subscriptions can be added as a new mod (VB SteamOnly).
        self.add_button.setEnabled(row["managed"] != "Yes")
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
