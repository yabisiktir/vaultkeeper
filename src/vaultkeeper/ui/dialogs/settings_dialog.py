"""SettingsDialog — the application preferences dialog (VB ``Settings``/``BasicSettings``).

Edits the persisted Vaultkeeper settings model (recycle-vs-permanent delete, the
startup config-drift check) on a **General** tab, an **Appearance** tab (VB
``MsFontAndColour``/``RbnFontAndColour`` — see ``ui/theme.py`` for the BOUNDED
PORT this represents: a global font size + light/dark/system theme, not the full
per-element VB font/colour editor), and — when a controller is supplied — shows
the resolved file paths on a **Locations** tab (VB Settings *Locations* page:
``Location`` / ``Path``). A modest but real slice of the full VB Settings form;
the Mapper editors (see the FolderMapping viewer) and run/web menus come later.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
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
        start_tab: str = "",
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
        self.tabs.addTab(self._build_behaviour(settings), "Behaviour")
        self.tabs.addTab(self._build_appearance(settings), "Appearance")
        self.tabs.addTab(self._build_web_menu(settings), "Web Menu")
        self.tabs.addTab(self._build_run_menu(settings), "Run Menu")
        self.locations = self._build_locations(controller)
        if self.locations is not None:
            self.tabs.addTab(self.locations, "Locations")
        layout.addWidget(self.tabs, 1)
        # Open on a named tab (VB SettingsStartPage — e.g. Basic Settings opens the
        # behaviour/UI preferences, Advanced opens the full settings).
        if start_tab:
            for index in range(self.tabs.count()):
                if self.tabs.tabText(index) == start_tab:
                    self.tabs.setCurrentIndex(index)
                    break

        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.addButton(
            help_button("BhBasicSettings", self), QDialogButtonBox.ButtonRole.HelpRole
        )
        # "Reset…" with the VB BtReset menu (Restore All / Restore <current page>).
        buttons.addButton(self._build_reset_button(), QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    #: Tabs whose preferences can be restored to defaults, tab title → builder.
    #: Locations is excluded — the game paths have no meaningful default.
    def _reset_builders(self) -> dict:
        return {
            "General": self._build_general,
            "Behaviour": self._build_behaviour,
            "Appearance": self._build_appearance,
            "Web Menu": self._build_web_menu,
            "Run Menu": self._build_run_menu,
        }

    def _build_reset_button(self):
        from PySide6.QtWidgets import QMenu, QToolButton

        button = QToolButton()
        button.setText("Reset…")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        self._reset_all_action = menu.addAction(
            "Restore All Settings to Default Values", self._on_reset_all
        )
        self._reset_panel_action = menu.addAction("Restore Panel", self._on_reset_panel)
        menu.aboutToShow.connect(self._update_reset_menu)
        button.setMenu(menu)
        self._reset_button = button
        return button

    def _update_reset_menu(self) -> None:
        """Label/enable the per-page reset for the current tab (VB CmsResetPanel)."""
        name = self.tabs.tabText(self.tabs.currentIndex())
        resettable = name in self._reset_builders()
        # VB: CmsResetPanel.Text = CmsResetAll.Text.Replace("All Settings", <page>).
        self._reset_panel_action.setText(f"Restore {name}")
        self._reset_panel_action.setEnabled(resettable)

    def _reset_settings(self) -> Settings:
        """Defaults for every editable preference, preserving identity settings.

        The game paths, active profile, store root, saved geometry, recent-mods
        counters, map overrides and any unknown keys are carried over from the
        current settings — only the user *preferences* are defaulted.
        """
        reset = Settings()
        src = self._settings
        for name in (
            "version", "store_root", "nwn_path", "game_user_path", "active_profile",
            "window_geometry", "max_recent_mods", "number_recent_mods",
            "map_overrides", "map_exclude_overrides",
        ):
            setattr(reset, name, getattr(src, name))
        reset._extra = dict(src._extra)
        return reset

    def _rebuild_tab(self, name: str, settings: Settings) -> None:
        build = self._reset_builders().get(name)
        if build is None:
            return
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == name:
                self.tabs.removeTab(index)
                self.tabs.insertTab(index, build(settings), name)
                self.tabs.setCurrentIndex(index)
                break

    def _on_reset_all(self) -> None:
        """Restore every preference tab to defaults (VB CmsResetAll)."""
        defaults = self._reset_settings()
        for name in self._reset_builders():
            self._rebuild_tab(name, defaults)

    def _on_reset_panel(self) -> None:
        """Restore only the current tab's preferences to defaults (VB CmsResetPanel)."""
        self._rebuild_tab(self.tabs.tabText(self.tabs.currentIndex()), self._reset_settings())

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

    def _build_behaviour(self, settings: Settings) -> QWidget:
        """Behaviour / User-Interface preferences (VB Settings Behaviour group)."""
        page = QWidget()
        form = QFormLayout(page)

        self.convert_bik = QCheckBox(
            "Convert .bik movies to .wbm when building an installer (NWN:EE)"
        )
        self.convert_bik.setChecked(settings.convert_bik_files)
        form.addRow(self.convert_bik)

        self.install_after_create = QCheckBox(
            "Install a mod automatically after creating its installer"
        )
        self.install_after_create.setChecked(settings.install_after_create)
        form.addRow(self.install_after_create)

        self.remember_window = QCheckBox(
            "Remember the window size and position between runs"
        )
        self.remember_window.setChecked(settings.remember_window_position)
        form.addRow(self.remember_window)

        self.startup_sound = QCheckBox("Play a sound when the application starts")
        self.startup_sound.setChecked(settings.startup_sound)
        form.addRow(self.startup_sound)

        self.default_group = QLineEdit(settings.default_group)
        self.default_group.setPlaceholderText("(ungrouped)")
        form.addRow("Default group for new mods:", self.default_group)

        self.move_added_mods = QCheckBox("Move mods added from files into the default group")
        self.move_added_mods.setChecked(settings.move_added_mods)
        form.addRow(self.move_added_mods)

        self.confirm_actions = QCheckBox("Ask for confirmation before destructive actions")
        self.confirm_actions.setChecked(settings.confirm_actions)
        form.addRow(self.confirm_actions)

        self.uninstall_dependencies = QCheckBox(
            "When uninstalling, also uninstall no-longer-needed dependencies"
        )
        self.uninstall_dependencies.setChecked(settings.uninstall_dependencies)
        form.addRow(self.uninstall_dependencies)

        self.display_image_files = QCheckBox("Preview image files in Display Info")
        self.display_image_files.setChecked(settings.display_image_files)
        form.addRow(self.display_image_files)

        self.delete_leto_logs = QCheckBox(
            "Move Leto log files to the recycle bin when the app starts"
        )
        self.delete_leto_logs.setChecked(settings.delete_leto_logs)
        form.addRow(self.delete_leto_logs)

        self.confirm_saves = QCheckBox("Ask before saving edited mod notes")
        self.confirm_saves.setChecked(settings.confirm_saves)
        form.addRow(self.confirm_saves)

        self.portrait_display_size = QComboBox()
        self.portrait_display_size.addItems(self._PORTRAIT_SIZE_LABELS)
        try:
            index = self._PORTRAIT_SIZE_LABELS.index(settings.portrait_display_size)
        except ValueError:
            index = 0
        self.portrait_display_size.setCurrentIndex(index)
        form.addRow("Character portrait size:", self.portrait_display_size)
        return page

    #: QComboBox item labels for ``self.theme``, in display order, mapped to the
    #: ``Settings.theme`` values in ``vaultkeeper.ui.theme.THEMES``.
    _THEME_LABELS = ("System", "Light", "Dark")

    #: Character-portrait size labels (VB ``ConfigPortraitDisplaySize`` H/L/M); the
    #: label is stored verbatim in ``Settings.portrait_display_size``.
    _PORTRAIT_SIZE_LABELS = ("Huge", "Large", "Medium")

    def _build_appearance(self, settings: Settings) -> QWidget:
        """Appearance preferences: BOUNDED PORT of the VB font/colour editor.

        VB opens a full ``BasicFontAndColourEditor`` (per-element Font page +
        Colour page). This ports only the high-value accessibility subset: one
        application-wide font point size and one light/dark/system theme. See
        ``vaultkeeper.ui.theme`` for the palette/font application logic.
        """
        from vaultkeeper.ui.theme import THEMES

        page = QWidget()
        form = QFormLayout(page)

        self.font_size = QSpinBox()
        self.font_size.setRange(0, 24)
        self.font_size.setSpecialValueText("System default")
        self.font_size.setValue(settings.font_point_size)
        form.addRow("Application font size:", self.font_size)

        self.theme = QComboBox()
        self.theme.addItems(self._THEME_LABELS)
        try:
            index = THEMES.index(settings.theme)
        except ValueError:
            index = 0
        self.theme.setCurrentIndex(index)
        form.addRow("Theme:", self.theme)
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

    def _build_run_menu(self, settings: Settings) -> QWidget:
        """Editable Run-menu programs (VB Settings RunMenu: Menu Text / Program path).

        Mirrors the Web-menu editor, but each entry is an external program to launch
        (label + executable path); **Browse…** picks the path for the selected row.
        """
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addWidget(
            QLabel("Programs shown in the Run menu (double-click a cell to edit):")
        )

        row = QHBoxLayout()
        self.run_tree = QTreeWidget()
        self.run_tree.setHeaderLabels(["Menu Text", "Program Path"])
        self.run_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.run_tree.setRootIsDecorated(False)
        for entry in settings.run_links:
            self._add_run_row(entry.get("text", ""), entry.get("path", ""))
        row.addWidget(self.run_tree, 1)

        buttons = QVBoxLayout()
        for label, slot in (
            ("Add", self._run_add),
            ("Browse…", self._run_browse),
            ("Remove", self._run_remove),
            ("Move Up", lambda: self._run_move(-1)),
            ("Move Down", lambda: self._run_move(1)),
            ("Reset", self._run_reset),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            buttons.addWidget(btn)
        buttons.addStretch(1)
        row.addLayout(buttons)
        outer.addLayout(row)
        return page

    def _add_run_row(self, text: str, path: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text, path])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.run_tree.addTopLevelItem(item)
        return item

    def _run_add(self) -> None:
        item = self._add_run_row("New Program", "")
        self.run_tree.setCurrentItem(item)
        self.run_tree.editItem(item, 0)

    def _run_browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        item = self.run_tree.currentItem()
        if item is None:
            item = self._add_run_row("New Program", "")
            self.run_tree.setCurrentItem(item)
        path, _ = QFileDialog.getOpenFileName(self, "Select program", item.text(1))
        if path:
            item.setText(1, path)

    def _run_remove(self) -> None:
        index = self.run_tree.indexOfTopLevelItem(self.run_tree.currentItem())
        if index >= 0:
            self.run_tree.takeTopLevelItem(index)

    def _run_move(self, delta: int) -> None:
        tree = self.run_tree
        index = tree.indexOfTopLevelItem(tree.currentItem())
        target = index + delta
        if index < 0 or not 0 <= target < tree.topLevelItemCount():
            return
        item = tree.takeTopLevelItem(index)
        tree.insertTopLevelItem(target, item)
        tree.setCurrentItem(item)

    def _run_reset(self) -> None:
        """Restore the default Run-menu programs (VB ResetRunMenu; empty by default)."""
        from vaultkeeper.config.settings import default_run_links

        self.run_tree.clear()
        for entry in default_run_links():
            self._add_run_row(entry.get("text", ""), entry.get("path", ""))

    def run_links(self) -> list[dict[str, str]]:
        """The current Run-menu programs from the tree (blank rows dropped)."""
        entries = []
        for i in range(self.run_tree.topLevelItemCount()):
            item = self.run_tree.topLevelItem(i)
            text, path = item.text(0).strip(), item.text(1).strip()
            if text or path:
                entries.append({"text": text, "path": path})
        return entries

    def _build_locations(self, controller) -> QWidget | None:
        if controller is None:
            self.game_install_edit = None
            self.game_user_edit = None
            return None
        report = controller.locations_report()
        by_location = {r["location"]: r["path"] for r in report["rows"]}

        page = QWidget()
        outer = QVBoxLayout(page)
        outer.addWidget(
            QLabel("Edit the game paths (Browse to a folder); other rows are resolved:")
        )

        form = QFormLayout()
        self.game_install_edit, install_row = self._path_editor(
            by_location.get("Game Installation", "")
        )
        form.addRow("Game Installation:", install_row)
        self.game_user_edit, user_row = self._path_editor(
            by_location.get("Game User Folder", "")
        )
        form.addRow("Game User Folder:", user_row)
        outer.addLayout(form)

        # Create a separate game folder for this profile (VB CreateNwnFolder).
        create_folder = QPushButton("Create New Game Folder…")
        create_folder.clicked.connect(self._on_create_nwn_folder)
        create_row = QHBoxLayout()
        create_row.addWidget(create_folder)
        create_row.addStretch(1)
        outer.addLayout(create_row)

        tree = QTreeWidget()
        tree.setHeaderLabels(["Location", "Path"])
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        groups: dict[str, QTreeWidgetItem] = {}
        for row in report["rows"]:
            parent = groups.get(row["group"])
            if parent is None:
                parent = QTreeWidgetItem([row["group"], ""])
                tree.addTopLevelItem(parent)
                groups[row["group"]] = parent
            parent.addChild(QTreeWidgetItem([row["location"], row["path"]]))
        tree.expandAll()
        outer.addWidget(tree, 1)
        return page

    def _path_editor(self, value: str):
        """A read/edit path field + Browse button; returns (QLineEdit, row widget)."""
        edit = QLineEdit(value)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._browse_into(edit))
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(edit, 1)
        rl.addWidget(browse)
        return edit, row

    def _browse_into(self, edit: QLineEdit) -> None:
        from PySide6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "Select folder", edit.text())
        if folder:
            edit.setText(folder)

    def _on_create_nwn_folder(self) -> None:
        """Create an isolated NWN game folder for this profile (VB CreateNwnFolder)."""
        from pathlib import Path

        from vaultkeeper.ui.dialogs.create_nwn_folder import CreateNwnFolderDialog

        controller = self._controller
        source = (self.game_install_edit.text() if self.game_install_edit else "").strip()
        profile = getattr(getattr(controller, "store_path", None), "stem", "") or ""
        parent_dir = str(Path(source).parent.parent) if source else ""
        is_ee = getattr(getattr(controller, "ctx", None), "is_ee", True)
        user_dir = (self.game_user_edit.text() if self.game_user_edit else "").strip()

        dlg = CreateNwnFolderDialog(
            profile_name=profile,
            source=source,
            parent_dir=parent_dir,
            is_ee=is_ee,
            config_ini_source=user_dir,
            parent=self,
        )
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        # Point this profile's Game Installation at the freshly-created folder.
        if accepted and dlg.created_path and self.game_install_edit is not None:
            self.game_install_edit.setText(dlg.created_path)

    def apply_to(self, settings: Settings) -> None:
        """Write the editable fields back into ``settings``."""
        settings.recycle_on_delete = self.recycle.isChecked()
        settings.validate_game_config_on_startup = self.startup_check.isChecked()
        settings.convert_bik_files = self.convert_bik.isChecked()
        settings.install_after_create = self.install_after_create.isChecked()
        settings.remember_window_position = self.remember_window.isChecked()
        settings.startup_sound = self.startup_sound.isChecked()
        settings.default_group = self.default_group.text().strip()
        settings.move_added_mods = self.move_added_mods.isChecked()
        settings.confirm_actions = self.confirm_actions.isChecked()
        settings.uninstall_dependencies = self.uninstall_dependencies.isChecked()
        settings.display_image_files = self.display_image_files.isChecked()
        settings.delete_leto_logs = self.delete_leto_logs.isChecked()
        settings.confirm_saves = self.confirm_saves.isChecked()
        settings.portrait_display_size = self.portrait_display_size.currentText()
        settings.font_point_size = self.font_size.value()
        from vaultkeeper.ui.theme import THEMES

        settings.theme = THEMES[self.theme.currentIndex()]
        settings.web_links = self.web_links()
        settings.run_links = self.run_links()
        if self.game_install_edit is not None:
            settings.nwn_path = self.game_install_edit.text().strip() or None
        if self.game_user_edit is not None:
            settings.game_user_path = self.game_user_edit.text().strip() or None

    @classmethod
    def edit(
        cls,
        settings_path=None,
        parent: QWidget | None = None,
        *,
        controller=None,
        start_tab: str = "",
    ) -> Settings | None:
        """Load settings, show the dialog modally, and persist on OK."""
        settings = load_settings(settings_path)
        dlg = cls(settings, parent, controller=controller, start_tab=start_tab)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to(settings)
            save_settings(settings, settings_path)
            return settings
        return None
