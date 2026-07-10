"""SettingsDialog — the application preferences dialog (VB ``Settings``/``BasicSettings``).

Edits the persisted Vaultkeeper settings model (recycle-vs-permanent delete, the
startup config-drift check) on a **General** tab, and — when a controller is
supplied — shows the resolved file paths on a **Locations** tab (VB Settings
*Locations* page: ``Location`` / ``Path``). A modest but real slice of the full VB
Settings form; the Mapper editors (see the FolderMapping viewer), run/web menus and
theming come later.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
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

from vaultkeeper.config.settings import (
    Settings,
    default_web_links,
    load_settings,
    save_settings,
)
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
        self.tabs.addTab(self._build_web_menu(settings), "Web Menu")
        self.locations = self._build_locations(controller)
        if self.locations is not None:
            self.tabs.addTab(self.locations, "Locations")
        layout.addWidget(self.tabs, 1)

        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.addButton(
            help_button("BhBasicSettings", self), QDialogButtonBox.ButtonRole.HelpRole
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

    def _build_web_menu(self, settings: Settings) -> QWidget:
        """Editable Web-menu links (VB Settings WebMenu: Menu Text / Web Address)."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addWidget(
            QLabel("Links shown in the Web menu (double-click a cell to edit):")
        )

        row = QHBoxLayout()
        self.web_tree = QTreeWidget()
        self.web_tree.setHeaderLabels(["Menu Text", "Web Address"])
        self.web_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.web_tree.setRootIsDecorated(False)
        for link in settings.web_links:
            self._add_web_row(link.get("text", ""), link.get("url", ""))
        row.addWidget(self.web_tree, 1)

        buttons = QVBoxLayout()
        for label, slot in (
            ("Add", self._web_add),
            ("Remove", self._web_remove),
            ("Move Up", lambda: self._web_move(-1)),
            ("Move Down", lambda: self._web_move(1)),
            ("Reset", self._web_reset),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            buttons.addWidget(btn)
        buttons.addStretch(1)
        row.addLayout(buttons)
        outer.addLayout(row)
        return page

    def _add_web_row(self, text: str, url: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text, url])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.web_tree.addTopLevelItem(item)
        return item

    def _web_add(self) -> None:
        item = self._add_web_row("New Link", "https://")
        self.web_tree.setCurrentItem(item)
        self.web_tree.editItem(item, 0)

    def _web_remove(self) -> None:
        index = self.web_tree.indexOfTopLevelItem(self.web_tree.currentItem())
        if index >= 0:
            self.web_tree.takeTopLevelItem(index)

    def _web_move(self, delta: int) -> None:
        tree = self.web_tree
        index = tree.indexOfTopLevelItem(tree.currentItem())
        target = index + delta
        if index < 0 or not 0 <= target < tree.topLevelItemCount():
            return
        item = tree.takeTopLevelItem(index)
        tree.insertTopLevelItem(target, item)
        tree.setCurrentItem(item)

    def _web_reset(self) -> None:
        self.web_tree.clear()
        for link in default_web_links():
            self._add_web_row(link["text"], link["url"])

    def web_links(self) -> list[dict[str, str]]:
        """The current Web-menu links from the tree (blank rows dropped)."""
        links = []
        for i in range(self.web_tree.topLevelItemCount()):
            item = self.web_tree.topLevelItem(i)
            text, url = item.text(0).strip(), item.text(1).strip()
            if text or url:
                links.append({"text": text, "url": url})
        return links

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
        settings.web_links = self.web_links()

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
