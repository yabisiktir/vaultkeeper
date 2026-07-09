"""SettingsDialog — the application preferences dialog (VB ``Settings``/``BasicSettings``).

Edits the persisted Vaultkeeper settings model (recycle-vs-permanent delete, the
startup config-drift check) on a **General** tab, and — when a controller is
supplied — shows the resolved file paths on a **Locations** tab (VB Settings
*Locations* page: ``Location`` / ``Path``). A modest but real slice of the full VB
Settings form; the Mapper editors (see the FolderMapping viewer), run/web menus and
theming come later.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.ui import resources as R


class SettingsDialog(QDialog):
    """Edit the persisted application preferences and view resolved locations."""

    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        *,
        controller=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setWindowIcon(R.get_icon("SettingsCogBlue"))
        self.resize(560, 380)
        self._settings = settings
        self._controller = controller

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general(settings), "General")
        self.locations = self._build_locations(controller)
        if self.locations is not None:
            self.tabs.addTab(self.locations, "Locations")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_general(self, settings: Settings) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.recycle = QCheckBox("Send deleted items to the Recycle Bin / Trash")
        self.recycle.setChecked(settings.recycle_on_delete)
        form.addRow(self.recycle)

        self.startup_check = QCheckBox(
            "Check the game configuration for changes on startup"
        )
        self.startup_check.setChecked(settings.validate_game_config_on_startup)
        form.addRow(self.startup_check)

        form.addRow("Neverwinter Nights folder:", QLabel(settings.nwn_path or "—"))
        form.addRow("Active profile:", QLabel(settings.active_profile or "—"))
        store = settings.store_root or str(settings.resolved_store().root)
        form.addRow("Vaultkeeper store:", QLabel(store))
        return page

    def _build_locations(self, controller) -> QTreeWidget | None:
        if controller is None:
            return None
        tree = QTreeWidget()
        tree.setHeaderLabels(["Location", "Path"])
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        report = controller.locations_report()
        groups: dict[str, QTreeWidgetItem] = {}
        for row in report["rows"]:
            parent = groups.get(row["group"])
            if parent is None:
                parent = QTreeWidgetItem([row["group"], ""])
                tree.addTopLevelItem(parent)
                groups[row["group"]] = parent
            parent.addChild(QTreeWidgetItem([row["location"], row["path"]]))
        tree.expandAll()
        return tree

    def apply_to(self, settings: Settings) -> None:
        """Write the editable fields back into ``settings``."""
        settings.recycle_on_delete = self.recycle.isChecked()
        settings.validate_game_config_on_startup = self.startup_check.isChecked()

    @classmethod
    def edit(
        cls,
        settings_path=None,
        parent: QWidget | None = None,
        *,
        controller=None,
    ) -> Settings | None:
        """Load settings, show the dialog modally, and persist on OK."""
        settings = load_settings(settings_path)
        dlg = cls(settings, parent, controller=controller)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to(settings)
            save_settings(settings, settings_path)
            return settings
        return None
