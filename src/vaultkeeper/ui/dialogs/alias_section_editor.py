"""AliasSectionEditor — view/edit the ``nwn.ini`` ``[Alias]`` folder locations.

Port of VB ``AliasSectionEditor``.

The ``[Alias]`` section tells Neverwinter Nights (and Vaultkeeper) where each moddable
folder physically lives. This editor lists those entries and lets the user point an alias
at a non-standard folder.

CONFIG-ISOLATION: ``nwn.ini`` is *game config*, which Vaultkeeper otherwise never writes.
Saving therefore requires an explicit confirmation, and the original file is backed up to
``nwn.ini.bak`` before the first write. Built on ``ProfileController.alias_locations_report``
/ ``save_alias_locations``.

BOUNDED PORT (noted): the VB editor also maintains a per-profile *Custom Alias Definitions*
file + state machine, a shared-vs-per-profile Game Saves toggle, mandatory-folder-name
validation, a reset-to-standard action, and restarts the app after saving. Here the editor
edits the existing ``[Alias]`` values in place and re-opens the profile so the new locations
take effect; the rest is deferred.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R


class AliasSectionEditor(QDialog):
    """Edit the ``nwn.ini`` ``[Alias]`` folder locations."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Alias Section Editor")
        self.setWindowIcon(R.get_icon("SettingsCogBlue"))
        self.resize(640, 460)
        #: Set True once a save actually changes nwn.ini (the caller re-opens the profile).
        self.changed = False

        report = controller.alias_locations_report()
        self._rows = report["rows"]
        self._exists = report["exists"]
        self._original = {r["key"]: r["value"] for r in self._rows}

        outer = QVBoxLayout(self)
        outer.addWidget(
            QLabel(
                "Custom folder locations for this game (nwn.ini [Alias] section).\n"
                "Double-click a location to edit it; Browse sets it to a folder."
            )
        )

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Alias", "Folder Location"])
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        header.setStretchLastSection(True)
        for row in self._rows:
            item = QTreeWidgetItem([row["key"], row["value"]])
            # Only the location (column 1) is editable; the alias key is fixed.
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.tree.addTopLevelItem(item)
        outer.addWidget(self.tree, 1)

        if not self._exists:
            note = QLabel(
                "No nwn.ini was found for this game, so there is nothing to edit."
                if not report["ini_path"]
                else f"nwn.ini not found:\n{report['ini_path']}"
            )
            note.setWordWrap(True)
            outer.addWidget(note)

        buttons = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhAliasEditor", self))
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self._on_browse)
        buttons.addWidget(self.browse_button)
        buttons.addStretch(1)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        self.save_button.setEnabled(self._exists)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.save_button)
        buttons.addWidget(close_button)
        outer.addLayout(buttons)

    def _on_browse(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        folder = QFileDialog.getExistingDirectory(
            self, f"Folder for {item.text(0)}", item.text(1)
        )
        if folder:
            item.setText(1, folder)

    def pending_updates(self) -> dict[str, str]:
        """Alias keys whose location was edited, mapped to the new value."""
        updates: dict[str, str] = {}
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            key, value = item.text(0), item.text(1).strip()
            if value != self._original.get(key, ""):
                updates[key] = value
        return updates

    def _on_save(self) -> None:
        updates = self.pending_updates()
        if not updates:
            QMessageBox.information(self, "Alias Section Editor", "No changes to save.")
            return
        # CONFIG-ISOLATION: confirm before writing the game's nwn.ini.
        confirm = QMessageBox.question(
            self,
            "Modify nwn.ini?",
            f"Vaultkeeper will update {len(updates)} folder location(s) in your game's "
            "nwn.ini [Alias] section.\n\nThe original file is backed up to nwn.ini.bak "
            "first. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        result = self._controller.save_alias_locations(updates)
        self.changed = result["changed"] > 0
        QMessageBox.information(self, "Alias Section Editor", result["message"])
        self.accept()

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> AliasSectionEditor:
        """Build and show the Alias Section editor for a controller's profile."""
        dlg = cls(controller, parent)
        dlg.show()
        return dlg
