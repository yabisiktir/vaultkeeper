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
from PySide6.QtGui import QColor, QCursor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
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
from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R


def _insert_after_current(tree: QTreeWidget, columns: list[str]) -> QTreeWidgetItem:
    """Add a row **after** the selected one (``bhwebmenu`` / ``bhrunmenu``).

    "Select the item that will precede your new entry… The new item is inserted
    after the entry you selected." These menus are ordered lists that people
    read top to bottom, so where a new entry lands is the feature; appending to
    the end meant clicking Move Up as many times as the list is long.
    """
    item = QTreeWidgetItem(columns)
    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
    current = tree.currentItem()
    index = tree.indexOfTopLevelItem(current) if current is not None else -1
    if index >= 0:
        tree.insertTopLevelItem(index + 1, item)
    else:
        tree.addTopLevelItem(item)
    tree.setCurrentItem(item)
    return item


def _install_actions_menu(tree: QTreeWidget, actions: list[tuple[str, object]]) -> None:
    """Right-click / Insert as the topics describe them.

    "Click the Edit Icon, Right-Click, Double-Click or press the Space Bar to
    access the actions menu." The buttons down the side do all of this already;
    what was missing is that right-clicking a list of things you are editing did
    nothing at all, which reads as a broken list rather than a different idiom.

    Insert is a widget shortcut, not a window one, so the inline editor these
    rows open keeps its own keys (see the Rename regression in
    ``ui/file_view.py``).
    """
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import QMenu

    # Built once and shown with popup() rather than exec(): the contents never
    # vary, and exec() is a nested event loop that a test cannot get out of —
    # QMenu.exec cannot be patched away in PySide6, it dispatches to C++ either
    # way and blocks forever.
    menu = QMenu(tree)
    for label, slot in actions:
        menu.addAction(label, slot)

    tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    tree.customContextMenuRequested.connect(
        lambda pos: menu.popup(tree.viewport().mapToGlobal(pos))
    )

    insert = QShortcut(QKeySequence(Qt.Key.Key_Insert), tree)
    insert.setContext(Qt.ShortcutContext.WidgetShortcut)
    insert.activated.connect(actions[0][1])


class _ColourButton(QPushButton):
    """One colour, with a swatch, a picker and a way back to the default.

    Right-click (or the Reset entry) clears the override rather than setting a
    colour that happens to match today's default: "unset" has to stay reachable,
    or the theme can never take the colour back.
    """

    def __init__(self, name: str, value: str = "") -> None:
        super().__init__()
        self._name = name
        self._value = value
        self.clicked.connect(self._pick)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _pos: self._menu())
        self._render()

    def value(self) -> str:
        return self._value

    def _current(self) -> QColor:
        from vaultkeeper.ui import theme

        if self._value:
            return QColor(self._value)
        return theme.status_colour(self._name)

    def _render(self) -> None:
        colour = self._current()
        pixmap = QPixmap(16, 16)
        pixmap.fill(colour)
        self.setIcon(QIcon(pixmap))
        self.setText(
            self._value.upper() if self._value else f"Theme default ({colour.name().upper()})"
        )

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(self._current(), self, "Choose a colour")
        if chosen.isValid():
            self._value = chosen.name()
            self._render()

    def _menu(self) -> None:
        menu = QMenu(self)
        reset = menu.addAction("Use the theme's colour")
        reset.setEnabled(bool(self._value))
        if menu.exec(QCursor.pos()) is reset:
            self._value = ""
            self._render()


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
        geometry.remember(self, "SettingsDialog", 560, 380)
        self._settings = settings
        self._controller = controller
        #: Profile → new game folder, from the Profiles page; applied on Save.
        self._profile_folder_edits: dict[str, str] = {}
        #: Profiles staged for removal, applied on Save.
        self._profiles_to_remove: set[str] = set()

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general(settings), "General")
        self.tabs.addTab(self._build_behaviour(settings), "Behaviour")
        self.tabs.addTab(self._build_downloads(settings), "Downloads")
        self.tabs.addTab(self._build_appearance(settings), "Appearance")
        self.tabs.addTab(self._build_web_menu(settings), "Web Menu")
        self.tabs.addTab(self._build_run_menu(settings), "Run Menu")
        self.tabs.addTab(self._build_viewer(settings), "Character / Save Viewer")
        self.locations = self._build_locations(controller)
        if self.locations is not None:
            self.tabs.addTab(self.locations, "Locations")
        self.tabs.addTab(self._build_profiles(settings), "Profiles")
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

        self._track_changes()

    # -- "Changed this session" (bhpreferences.htm) ------------------------ #
    def _track_changes(self) -> None:
        """Italicise anything altered since the dialog opened.

        "Preferences you change during your current Settings session are
        displayed in italics." Across nine tabs of check boxes that is the
        difference between knowing what you are about to save and hoping — and
        it costs nothing to be sure, where re-reading every page does not.

        Baselines are captured once and compared on every change, so putting a
        setting back the way it was clears the mark rather than leaving a false
        one.
        """
        from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QSpinBox

        readers = (
            (QCheckBox, lambda w: w.isChecked(), lambda w: w.toggled),
            (QLineEdit, lambda w: w.text(), lambda w: w.textChanged),
            (QSpinBox, lambda w: w.value(), lambda w: w.valueChanged),
            (QComboBox, lambda w: w.currentIndex(), lambda w: w.currentIndexChanged),
        )
        self._changed_baseline: dict = {}
        for kind, read, signal in readers:
            for widget in self.findChildren(kind):
                # A combo's line edit and a spin box's are the same value twice.
                if isinstance(widget, QLineEdit) and isinstance(
                    widget.parent(), (QComboBox, QSpinBox)
                ):
                    continue
                self._changed_baseline[widget] = read(widget)
                signal(widget).connect(
                    lambda *_a, w=widget, r=read: self._mark_changed(w, r(w))
                )

    def _mark_changed(self, widget, value) -> None:
        font = widget.font()
        font.setItalic(value != self._changed_baseline.get(widget))
        widget.setFont(font)

    def changed_widgets(self) -> list:
        """Everything currently marked as changed (what the italics say)."""
        return [w for w in self._changed_baseline if w.font().italic()]

    #: Tabs whose preferences can be restored to defaults, tab title → builder.
    #: Locations is excluded — the game paths have no meaningful default.
    def _reset_builders(self) -> dict:
        return {
            "General": self._build_general,
            "Behaviour": self._build_behaviour,
            "Downloads": self._build_downloads,
            "Appearance": self._build_appearance,
            "Web Menu": self._build_web_menu,
            "Run Menu": self._build_run_menu,
            "Character / Save Viewer": self._build_viewer,
        }

    def _build_reset_button(self):
        # A QPushButton, not a QToolButton: a tool button does not size itself
        # for its label plus the menu arrow, so "Reset…" rendered clipped inside
        # a box a third too narrow, next to full-size Help/Cancel/OK. A push
        # button with a menu sizes correctly and matches the buttons beside it.
        from PySide6.QtWidgets import QMenu, QPushButton

        button = QPushButton("Reset…")
        button.setAutoDefault(False)  # Enter belongs to OK, not to opening a menu
        menu = QMenu(button)
        self._reset_all_action = menu.addAction(
            "Restore All Settings to Default Values", self._on_reset_all
        )
        self._reset_panel_action = menu.addAction("Restore Panel", self._on_reset_panel)

        # VB's Settings screen carries Export and Import beside Reset (TsExport /
        # TsImport); on first run it even opens here and clicks Import for you
        # when the store already holds exported settings. Both are wholesale
        # replacements of the current preferences, which is why they sit
        # together.
        menu.addSeparator()
        self._export_action = menu.addAction(
            R.get_icon("ExportSettings_x32"), "Export Settings…", self._on_export
        )
        self._import_action = menu.addAction(
            R.get_icon("Arrow_ImportOrLoad_16x_color"), "Import Settings…", self._on_import
        )
        for action in (self._export_action, self._import_action):
            action.setEnabled(self._controller is not None)

        menu.aboutToShow.connect(self._update_reset_menu)
        button.setMenu(menu)
        self._reset_button = button
        return button

    def _on_export(self) -> None:
        """Export the preferences as they stand, including unsaved edits.

        The dialog's own widgets are folded back into the settings first —
        exporting what is on disk while the user is looking at something else on
        screen would export the wrong thing.
        """
        from PySide6.QtWidgets import QMessageBox

        self.apply_to(self._settings)
        from vaultkeeper.config.settings import save_settings

        save_settings(self._settings, getattr(self._controller, "_settings_path", None))
        result = self._controller.export_settings()
        QMessageBox.information(self, "Export Settings", result["message"])

    def _on_import(self) -> None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        exported = self._controller.exported_settings_files()
        start = str(exported[0].parent) if exported else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", start, "Exported settings (*.json);;All files (*)"
        )
        if not path:
            return
        from pathlib import Path

        result = self._controller.import_settings(Path(path))
        QMessageBox.information(self, "Import Settings", result["message"])
        if result["ok"]:
            # Re-open on the imported values rather than leaving stale widgets
            # over settings that have already changed underneath them.
            from vaultkeeper.config.settings import load_settings

            imported = load_settings(getattr(self._controller, "_settings_path", None))
            for name in self._reset_builders():
                self._rebuild_tab(name, imported)
            self._settings = imported

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

        self.recycle_saves = QCheckBox("…including deleted game saves")
        self.recycle_saves.setChecked(settings.recycle_game_saves)
        self.recycle_saves.setToolTip(
            "Game saves are large and routinely discarded, so they get their own "
            "answer."
        )
        form.addRow(self.recycle_saves)

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

        self.use_move_on_add = QCheckBox(
            "Use Move when adding files to a mod (unchecked copies instead)"
        )
        self.use_move_on_add.setChecked(settings.use_move_on_add)
        self.use_move_on_add.setToolTip(
            "On: added files are moved out of their source folder.\n"
            "Off: they are copied, leaving the originals in place."
        )
        form.addRow(self.use_move_on_add)

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

    #: How a Vault project is read, in display order, mapped to the
    #: ``Settings.vault_download_method`` values.
    _DOWNLOAD_METHODS = ("api", "scrape")
    _DOWNLOAD_METHOD_LABELS = (
        "The Vault's API (recommended)",
        "Read the project's web page",
    )

    def _build_downloads(self, settings: Settings) -> QWidget:
        """How Vault projects are read, and where the download rules come from."""
        page = QWidget()
        form = QFormLayout(page)

        self.vault_download_method = QComboBox()
        self.vault_download_method.addItems(self._DOWNLOAD_METHOD_LABELS)
        try:
            index = self._DOWNLOAD_METHODS.index(
                (settings.vault_download_method or "api").lower()
            )
        except ValueError:
            index = 0
        self.vault_download_method.setCurrentIndex(index)
        self.vault_download_method.setToolTip(
            "The API states each file's real name and size in one request, and "
            "keeps working when the Vault redesigns its pages — which is why the "
            "original tool moved to it. Reading the page is the older method, "
            "kept as a fallback."
        )
        form.addRow("Read Vault projects using:", self.vault_download_method)

        self.vault_rules_online = QCheckBox("Keep the Vault download rules up to date")
        self.vault_rules_online.setChecked(settings.vault_rules_online)
        self.vault_rules_online.setToolTip(
            "The download rules are published online, and carry the Vault's API "
            "addresses and per-project fixes. Fetching them (at most once a day) "
            "is how a change at the Vault is picked up without a new release. "
            "Turn this off to use only the copy already on this machine."
        )
        form.addRow(self.vault_rules_online)

        self.vault_apply_project_rules = QCheckBox(
            "Use the rules' per-project mod folder, group and file choices"
        )
        self.vault_apply_project_rules.setChecked(settings.vault_apply_project_rules)
        self.vault_apply_project_rules.setToolTip(
            "The rules say which mod folder and group a known project belongs in, "
            "which of its files are the ones wanted, and which are superseded and "
            "should not be offered. Turn this off to take a project exactly as the "
            "Vault presents it."
        )
        form.addRow(self.vault_apply_project_rules)

        from vaultkeeper.vault import rules_source

        hosts = QLabel(
            "Published at:<br>"
            + "<br>".join(
                f"&nbsp;&nbsp;{name}: {url}" for name, url in rules_source.rules_urls()
            )
        )
        hosts.setWordWrap(True)
        hosts.setEnabled(False)  # informational, not editable
        form.addRow(hosts)
        return page

    def _build_viewer(self, settings: Settings) -> QWidget:
        """Character Explorer / Save Game Editor display preferences."""
        page = QWidget()
        form = QFormLayout(page)

        self.inventory_nwn_style = QCheckBox(
            "Show inventory as an NWN-style item icon grid (instead of a list)"
        )
        self.inventory_nwn_style.setChecked(settings.inventory_nwn_style)
        form.addRow(self.inventory_nwn_style)

        self.exact_item_icons = QCheckBox(
            "Show each item's own icon, worked out from the game files"
        )
        self.exact_item_icons.setChecked(settings.exact_item_icons)
        self.exact_item_icons.setToolTip(
            "Match what the game shows: a suit of armour pictured by its own "
            "torso, a potion by its three stacked parts, a cloak by its variant. "
            "Turn this off to give every item of a type the same default picture."
        )
        form.addRow(self.exact_item_icons)

        self.hak_item_icons = QCheckBox(
            "Use custom item icons from installed haks (CEP/PRC)"
        )
        self.hak_item_icons.setChecked(settings.hak_item_icons)
        self.hak_item_icons.setToolTip(
            "Also search your hak folder for item icons, so custom items get their "
            "own picture instead of a generic base-game one. The first inventory you "
            "open scans every hak (~half a second); off by default."
        )
        form.addRow(self.hak_item_icons)

        # Portrait Manager. VB keeps these on the Advanced Settings *Locations*
        # page; they sit here because this is the port's viewer/tools tab and
        # both are about what an image tool shows you.
        self.tga_editor_path = QLineEdit(settings.tga_editor_path)
        self.tga_editor_path.setPlaceholderText("(none — Edit Portrait stays hidden)")
        self.tga_editor_path.setToolTip(
            "An image editor to open a portrait's five TGA files in. The Portrait "
            "Manager's Edit Portrait action only appears once this is set, as in "
            "the original tool."
        )
        form.addRow("TGA file editor:", self.tga_editor_path)

        self.portrait_image_web_page = QLineEdit(settings.portrait_image_web_page)
        self.portrait_image_web_page.setPlaceholderText("(none — the link stays hidden)")
        self.portrait_image_web_page.setToolTip(
            "A site you source portrait images from; the Portrait Manager offers a "
            "button that opens it."
        )
        form.addRow("Portrait image web page:", self.portrait_image_web_page)

        return page

    #: QComboBox item labels for ``self.theme``, in display order, mapped to the
    #: ``Settings.theme`` values in ``vaultkeeper.ui.theme.THEMES``.
    _THEME_LABELS = ("System", "Light", "Dark")

    #: Character-portrait size labels (VB ``ConfigPortraitDisplaySize`` H/L/M); the
    #: label is stored verbatim in ``Settings.portrait_display_size``.
    _PORTRAIT_SIZE_LABELS = ("Huge", "Large", "Medium")

    def _build_appearance(self, settings: Settings) -> QWidget:
        """Appearance: the Font and Colour pages (VB ``BasicFontAndColourEditor``).

        VB keeps a font per UI element (11 of them) and a colour per element
        (25). This offers one font and the **four colours this application
        actually paints with** — the mod-list status colours. The other twenty-one
        would be pickers for colours nothing reads, which is a preference that
        lies to the person setting it; see ``vaultkeeper.ui.theme``.
        """
        from PySide6.QtGui import QFontDatabase

        from vaultkeeper.ui.theme import STATUS_COLOUR_LABELS, THEMES

        page = QWidget()
        form = QFormLayout(page)

        # A plain combo, not a QFontComboBox: that one owns its model and drops
        # an inserted row, and the first row has to be "leave the platform
        # alone" — the system font is not a family we can name on every OS.
        self.font_family = QComboBox()
        self.font_family.addItem("System default")
        self.font_family.addItems(QFontDatabase.families())
        if settings.font_family:
            index = self.font_family.findText(settings.font_family)
            self.font_family.setCurrentIndex(max(index, 0))
        form.addRow("Application font:", self.font_family)

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

        self._colour_buttons: dict[str, _ColourButton] = {}
        for name, (label, description) in STATUS_COLOUR_LABELS.items():
            button = _ColourButton(name, settings.status_colours.get(name, ""))
            button.setToolTip(description)
            self._colour_buttons[name] = button
            form.addRow(f"{label} colour:", button)
        note = QLabel(
            "Colours mark a mod's state in the list. Leave one alone and it "
            "follows the theme, staying readable on both backgrounds; set one "
            "and it is used as given."
        )
        note.setWordWrap(True)
        note.setEnabled(False)
        form.addRow("", note)
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
        _install_actions_menu(
            self.web_tree,
            [
                ("New Menu Item", self._web_add),
                ("Remove", self._web_remove),
                ("Move Up", lambda: self._web_move(-1)),
                ("Move Down", lambda: self._web_move(1)),
            ],
        )
        return page

    def _add_web_row(self, text: str, url: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text, url])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.web_tree.addTopLevelItem(item)
        return item

    def _web_add(self) -> None:
        item = _insert_after_current(self.web_tree, ["New Link", "https://"])
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
        _install_actions_menu(
            self.run_tree,
            [
                ("New Menu Item", self._run_add),
                ("Browse…", self._run_browse),
                ("Remove", self._run_remove),
                ("Move Up", lambda: self._run_move(-1)),
                ("Move Down", lambda: self._run_move(1)),
            ],
        )
        return page

    def _add_run_row(self, text: str, path: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text, path])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.run_tree.addTopLevelItem(item)
        return item

    def _run_add(self) -> None:
        item = _insert_after_current(self.run_tree, ["New Program", ""])
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

    def _build_profiles(self, settings: Settings) -> QWidget:
        """The Profiles page (VB Settings ``LvProfiles``).

        What each profile is *for*: which Neverwinter Nights it plays, and which
        edition it was made as. The folder is editable here because a test
        installation moves; the edition is not, because "You cannot change the
        Profile Type after the Profile has been created" — every file key the
        profile holds was written against the layout it chose.
        """
        from vaultkeeper.ui.session import list_profiles

        page = QWidget()
        layout = QVBoxLayout(page)
        note = QLabel(
            "Each profile plays a specific Neverwinter Nights installation, so a "
            "test or development copy need not disturb the one you play."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self.profiles_tree = QTreeWidget()
        self.profiles_tree.setHeaderLabels(["Profile", "Edition", "Neverwinter Nights"])
        self.profiles_tree.setRootIsDecorated(False)
        self.profiles_tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        for name in list_profiles(settings):
            is_ee = (settings.profile_editions or {}).get(name, True)
            folder = (settings.profile_game_paths or {}).get(name) or settings.nwn_path or ""
            item = QTreeWidgetItem(
                [name, "Enhanced Edition" if is_ee else "Neverwinter Nights", folder]
            )
            if name == settings.active_profile:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                item.setToolTip(0, "The profile currently loaded")
            self.profiles_tree.addTopLevelItem(item)
        self.profiles_tree.itemSelectionChanged.connect(self._sync_profile_buttons)
        layout.addWidget(self.profiles_tree, 1)

        row = QHBoxLayout()
        self.profile_folder_button = QPushButton("Neverwinter Nights Folder…")
        self.profile_folder_button.setToolTip(
            "Point this profile at a different installation"
        )
        self.profile_folder_button.clicked.connect(self._on_change_profile_folder)
        row.addWidget(self.profile_folder_button)
        # createaneverwinternightsfolder.htm puts this here, per profile —
        # making the folder and pointing the profile at it is one action, and
        # the Locations page's copy can only ever affect the loaded profile.
        self.profile_create_button = QPushButton("Create Game Folder…")
        self.profile_create_button.setToolTip(
            "Clone an installation into a new folder for this profile, so a test "
            "setup cannot disturb the one you play"
        )
        self.profile_create_button.clicked.connect(self._on_create_profile_folder)
        row.addWidget(self.profile_create_button)
        self.profile_remove_button = QPushButton("Remove…")
        self.profile_remove_button.setToolTip(
            "Delete this profile's mods and database when you click OK"
        )
        self.profile_remove_button.clicked.connect(self._on_remove_profile)
        row.addWidget(self.profile_remove_button)
        self.profile_rename_button = QPushButton("Rename…")
        self.profile_rename_button.clicked.connect(self._on_rename_profile)
        row.addWidget(self.profile_rename_button)
        row.addStretch(1)
        layout.addLayout(row)
        self._sync_profile_buttons()
        return page

    def _sync_profile_buttons(self) -> None:
        item = self.profiles_tree.currentItem()
        has_profile = item is not None
        staged = has_profile and item.text(0) in self._profiles_to_remove
        self.profile_folder_button.setEnabled(has_profile and not staged)
        self.profile_create_button.setEnabled(has_profile and not staged)
        # The loaded profile cannot be removed from under the running window.
        self.profile_remove_button.setEnabled(
            has_profile and item.text(0) != self._settings.active_profile
        )
        self.profile_remove_button.setText("Keep" if staged else "Remove…")
        # Renaming moves folders on disk, so it happens now rather than being
        # staged — and a profile staged for removal is not worth renaming.
        self.profile_rename_button.setEnabled(has_profile and not staged)

    def _on_rename_profile(self) -> None:
        """Rename a profile's folders and its records (``renameaprofile.htm``)."""
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        from vaultkeeper.ui.session import rename_profile

        item = self.profiles_tree.currentItem()
        if item is None:
            return
        old_name = item.text(0)
        new_name, ok = QInputDialog.getText(
            self, "Rename Profile", "New name:", text=old_name
        )
        if not ok or not new_name.strip():
            return
        result = rename_profile(old_name, new_name.strip(), self._settings)
        if not result["ok"]:
            QMessageBox.warning(self, "Rename Profile", result["message"])
            return
        item.setText(0, new_name.strip())
        # Any staged change follows the new name, or it would be applied to a
        # profile that no longer answers to the old one.
        if old_name in self._profile_folder_edits:
            self._profile_folder_edits[new_name.strip()] = self._profile_folder_edits.pop(
                old_name
            )

    def _on_remove_profile(self) -> None:
        """Stage a profile for removal, applied on OK (VB "flagged for deletion").

        Staged rather than done immediately, as VB does: this deletes a whole
        collection of mods, and Cancel has to mean cancel.
        """
        from PySide6.QtWidgets import QMessageBox

        item = self.profiles_tree.currentItem()
        if item is None:
            return
        name = item.text(0)
        if name in self._profiles_to_remove:
            self._profiles_to_remove.discard(name)
            font = item.font(0)
            font.setStrikeOut(False)
            for column in range(3):
                item.setFont(column, font)
            self._sync_profile_buttons()
            return
        if (
            QMessageBox.question(
                self,
                "Remove Profile",
                f"Remove '{name}' when you click OK?\n\n"
                "Its mods and its database are deleted — everything that profile "
                "installed from, not only its record.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._profiles_to_remove.add(name)
        font = item.font(0)
        font.setStrikeOut(True)
        for column in range(3):
            item.setFont(column, font)
        self._sync_profile_buttons()

    def _on_create_profile_folder(self) -> None:
        """Create a game folder for the selected profile and point it there."""
        from pathlib import Path

        from vaultkeeper.ui.dialogs.create_nwn_folder import CreateNwnFolderDialog

        item = self.profiles_tree.currentItem()
        if item is None:
            return
        name, source = item.text(0), item.text(2)
        dlg = CreateNwnFolderDialog(
            profile_name=name,
            source=source,
            parent_dir=str(Path(source).parent.parent) if source else "",
            is_ee=item.text(1) == "Enhanced Edition",
            config_ini_source=self._settings.game_user_path or "",
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.created_path:
            return
        item.setText(2, dlg.created_path)
        self._profile_folder_edits[name] = dlg.created_path

    def _on_change_profile_folder(self) -> None:
        """Repoint one profile at another installation, leaving the rest alone."""
        item = self.profiles_tree.currentItem()
        if item is None:
            return
        from PySide6.QtWidgets import QFileDialog

        chosen = QFileDialog.getExistingDirectory(
            self,
            f"Neverwinter Nights installation for '{item.text(0)}'",
            item.text(2),
        )
        if not chosen:
            return
        item.setText(2, chosen)
        self._profile_folder_edits[item.text(0)] = chosen

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
            QLabel(
                "Edit the paths below with Browse; the rows underneath are resolved "
                "from them and shown for reference."
            )
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

        # VB Locations, Installer Tool group: "NIT Start-up Sound", a *.wav file
        # picker whose Reset default is the game's own launcher fanfare.
        self.startup_sound_edit, sound_row = self._path_editor(
            self._settings.startup_sound_path, file_filter="Sound files (*.wav)"
        )
        self.startup_sound_edit.setPlaceholderText(
            self._default_startup_sound(controller) or "(no sound file found)"
        )
        self.startup_sound_edit.setToolTip(
            "The sound to play when Vaultkeeper starts. Leave blank for the one "
            "the Neverwinter Nights launcher plays. Only used when “Play a "
            "sound when the application starts” is ticked, under Behaviour."
        )
        form.addRow("Start-up sound:", sound_row)
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

    @staticmethod
    def _default_startup_sound(controller) -> str:
        """The game's own fanfare, shown as the placeholder (VB's Reset default)."""
        from vaultkeeper.game.startup_sound import default_sound

        game_root = getattr(getattr(controller, "ctx", None), "game_root", None)
        found = default_sound(game_root)
        return str(found) if found else ""

    def _path_editor(self, value: str, *, file_filter: str = ""):
        """A read/edit path field + Browse button; returns (QLineEdit, row widget).

        With ``file_filter`` the Browse button picks a *file* rather than a
        folder — VB distinguishes these as ``LocType.File`` and ``LocType.Path``.
        """
        edit = QLineEdit(value)
        browse = QPushButton("Browse…")
        if file_filter:
            browse.clicked.connect(lambda: self._browse_file_into(edit, file_filter))
        else:
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

    def _browse_file_into(self, edit: QLineEdit, file_filter: str) -> None:
        from PySide6.QtWidgets import QFileDialog

        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select file", edit.text(), file_filter
        )
        if chosen:
            edit.setText(chosen)

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
        # Per-profile folders edited on the Profiles page. Only the ones that
        # were actually changed, so an untouched profile keeps whatever it had.
        if self._profile_folder_edits:
            settings.profile_game_paths = {
                **settings.profile_game_paths,
                **self._profile_folder_edits,
            }
            active = settings.active_profile
            if active in self._profile_folder_edits:
                settings.nwn_path = self._profile_folder_edits[active]
        settings.recycle_on_delete = self.recycle.isChecked()
        settings.recycle_game_saves = self.recycle_saves.isChecked()
        settings.validate_game_config_on_startup = self.startup_check.isChecked()
        settings.convert_bik_files = self.convert_bik.isChecked()
        settings.install_after_create = self.install_after_create.isChecked()
        settings.remember_window_position = self.remember_window.isChecked()
        settings.startup_sound = self.startup_sound.isChecked()
        settings.default_group = self.default_group.text().strip()
        settings.move_added_mods = self.move_added_mods.isChecked()
        settings.use_move_on_add = self.use_move_on_add.isChecked()
        settings.confirm_actions = self.confirm_actions.isChecked()
        settings.uninstall_dependencies = self.uninstall_dependencies.isChecked()
        settings.display_image_files = self.display_image_files.isChecked()
        settings.delete_leto_logs = self.delete_leto_logs.isChecked()
        settings.confirm_saves = self.confirm_saves.isChecked()
        settings.portrait_display_size = self.portrait_display_size.currentText()
        settings.inventory_nwn_style = self.inventory_nwn_style.isChecked()
        settings.hak_item_icons = self.hak_item_icons.isChecked()
        settings.tga_editor_path = self.tga_editor_path.text().strip()
        settings.portrait_image_web_page = self.portrait_image_web_page.text().strip()
        settings.exact_item_icons = self.exact_item_icons.isChecked()
        settings.vault_download_method = self._DOWNLOAD_METHODS[
            self.vault_download_method.currentIndex()
        ]
        settings.vault_rules_online = self.vault_rules_online.isChecked()
        settings.vault_apply_project_rules = self.vault_apply_project_rules.isChecked()
        settings.font_point_size = self.font_size.value()
        settings.font_family = (
            self.font_family.currentText() if self.font_family.currentIndex() else ""
        )
        settings.status_colours = {
            name: button.value()
            for name, button in self._colour_buttons.items()
            if button.value()
        }
        from vaultkeeper.ui.theme import THEMES

        settings.theme = THEMES[self.theme.currentIndex()]
        settings.web_links = self.web_links()
        settings.run_links = self.run_links()
        if self.game_install_edit is not None:
            settings.nwn_path = self.game_install_edit.text().strip() or None
        if self.game_user_edit is not None:
            settings.game_user_path = self.game_user_edit.text().strip() or None
        if getattr(self, "startup_sound_edit", None) is not None:
            # VB Settings.Locations:173 skips PathStartupSound when the file does
            # not exist, rather than saving a path to nothing. Blank is different
            # from wrong, and means "use the game's own".
            from pathlib import Path

            chosen = self.startup_sound_edit.text().strip()
            if not chosen:
                settings.startup_sound_path = ""
            elif Path(chosen).is_file():
                settings.startup_sound_path = chosen

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
            # Profiles staged on the Profiles page. After the save, so a failure
            # here cannot lose the rest of the preferences.
            dlg.apply_profile_removals(settings, settings_path)
            return settings
        return None

    def apply_profile_removals(self, settings: Settings, settings_path=None) -> list[str]:
        """Delete the profiles staged for removal. Returns what each one said."""
        from vaultkeeper.ui.session import delete_profile

        messages = []
        for name in sorted(self._profiles_to_remove):
            result = delete_profile(name, settings, settings_path=settings_path)
            messages.append(result["message"])
        self._profiles_to_remove.clear()
        return messages
