"""BasicSettingsDialog — the curated Basic Settings dialog (VB ``BasicSettings``).

A small two-tab dialog (Behaviour / User Interface) exposing the handful of common
preferences, distinct from the full per-preference **Advanced** Settings browser
(``SettingsDialog``).  The **Advanced** button chains into that full dialog exactly
as the VB ``BtAdvanced`` does (``DialogResult.Yes`` → ``MsSettings.PerformClick``).

Faithful to the VB control set and captions.  Divergences (documented): the theme
picker is a simple combo (VB ``PicCheckBox`` opened a colour context menu), the
DebugMode command is fixed to ``"DebugMode 1"`` (VB let you pick the command), and
the "Selection" cross-link to the main window's text-file button is omitted.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.ui import geometry

_DEBUG_MODE_COMMAND = "DebugMode 1"


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


class BasicSettingsDialog(QDialog):
    """Curated Behaviour / User Interface preferences (VB BasicSettings)."""

    #: Set to True on accept when the user clicked **Advanced** (chain to Settings).
    advanced_requested: bool

    def __init__(
        self, settings: Settings, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self.advanced_requested = False
        self.setWindowTitle("Basic Settings")
        geometry.remember(self, "BasicSettingsDialog", 560, 460)

        layout = QVBoxLayout(self)
        layout.addWidget(
            _heading("Change selected Behaviour and User Interface Preferences")
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(self._behaviour_tab(), "Behaviour")
        self.tabs.addTab(self._user_interface_tab(), "User Interface")
        layout.addWidget(self.tabs, 1)

        # Bottom bar: Help … Advanced | Apply | Cancel  (VB button row).
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        bar = QHBoxLayout()
        bar.addWidget(help_button("BhBasicSettings", self))
        bar.addStretch(1)
        from PySide6.QtWidgets import QPushButton

        advanced = QPushButton("Advanced")
        advanced.clicked.connect(self._on_advanced)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._on_apply)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bar.addWidget(advanced)
        bar.addWidget(apply_btn)
        bar.addWidget(cancel)
        layout.addLayout(bar)

    # -- tabs ------------------------------------------------------------- #
    def _behaviour_tab(self) -> QWidget:
        tab = QWidget()
        v = QVBoxLayout(tab)

        v.addWidget(_heading("Install action to take after creating Mod Installers"))
        self.cb_install_auto = QCheckBox("Always install Mods")
        self.cb_install_auto.setChecked(self._settings.install_after_create)
        self.cb_install_auto.toggled.connect(self._couple_install)
        self.cb_install_restore = QCheckBox("Only install Mods that were already installed")
        self.cb_install_restore.setChecked(self._settings.installer_restore)
        self.cb_install_restore.toggled.connect(self._couple_install)
        v.addWidget(self.cb_install_auto)
        v.addWidget(self.cb_install_restore)

        v.addWidget(_heading("Actions to take when you start the Installer Tool"))
        self.rb_window_restore = QRadioButton("Restore Window position and layout")
        self.rb_window_default = QRadioButton("Use default Window position and layout")
        self.rb_window_restore.setChecked(self._settings.remember_window_position)
        self.rb_window_default.setChecked(not self._settings.remember_window_position)
        window_group = QButtonGroup(tab)
        window_group.addButton(self.rb_window_restore)
        window_group.addButton(self.rb_window_default)
        v.addWidget(self.rb_window_restore)
        v.addWidget(self.rb_window_default)
        self.cb_start_sound = QCheckBox("Play the start-up sound")
        self.cb_start_sound.setChecked(self._settings.startup_sound)
        v.addWidget(self.cb_start_sound)

        v.addWidget(
            _heading("Actions to take when you start and close Neverwinter Nights")
        )
        self.cb_select_game_mod = QCheckBox(
            "Select the Mod being played when you press Play Neverwinter Nights"
        )
        self.cb_select_game_mod.setChecked(self._settings.select_game_mod)
        self.cb_auto_character = QCheckBox(
            "Create Character Restorers automatically when you close Neverwinter Nights"
        )
        self.cb_auto_character.setChecked(self._settings.auto_character)
        self.cb_copy_debug = QCheckBox(
            "Copy DebugMode 1 to the clipboard when playing an existing Neverwinter "
            "Nights game"
        )
        self.cb_copy_debug.setChecked(bool(self._settings.copy_debug_mode_on_play))
        self.cb_copy_mod_name = QCheckBox(
            "Copy the Mod name to the clipboard when starting a new Neverwinter Nights game"
        )
        self.cb_copy_mod_name.setChecked(self._settings.copy_mod_name_on_play)
        for cb in (
            self.cb_select_game_mod,
            self.cb_auto_character,
            self.cb_copy_debug,
            self.cb_copy_mod_name,
        ):
            v.addWidget(cb)
        v.addStretch(1)
        return tab

    def _user_interface_tab(self) -> QWidget:
        tab = QWidget()
        v = QVBoxLayout(tab)

        v.addWidget(_heading("Thickness of line used to change panel size"))
        self.splitter_group = QButtonGroup(tab)
        self._splitter_radios: list[QRadioButton] = []
        for width, label in (
            (1, "Default line thickness"),
            (2, "Medium line thickness"),
            (3, "Large line thickness"),
            (4, "Extra large line thickness"),
        ):
            rb = QRadioButton(label)
            rb.setProperty("splitter_width", width)
            rb.setChecked(self._settings.splitter_width == width)
            self.splitter_group.addButton(rb)
            self._splitter_radios.append(rb)
            v.addWidget(rb)
        if not any(rb.isChecked() for rb in self._splitter_radios):
            self._splitter_radios[0].setChecked(True)

        v.addSpacing(8)
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        for value, label in (("system", "System"), ("light", "Light"), ("dark", "Dark")):
            self.theme_combo.addItem(label, value)
        idx = max(0, self.theme_combo.findData(self._settings.theme))
        self.theme_combo.setCurrentIndex(idx)
        theme_row.addWidget(self.theme_combo)
        theme_row.addStretch(1)
        v.addLayout(theme_row)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        v.addWidget(line)
        v.addStretch(1)
        return tab

    # -- coupling (VB CbCommon_CheckedChanged) ---------------------------- #
    def _couple_install(self, *_a: object) -> None:
        # VB: enabling "Always install" forces "Only install already-installed" on.
        if self.cb_install_auto.isChecked() and not self.cb_install_restore.isChecked():
            self.cb_install_restore.setChecked(True)

    # -- actions ---------------------------------------------------------- #
    def _selected_splitter_width(self) -> int:
        for rb in self._splitter_radios:
            if rb.isChecked():
                return int(rb.property("splitter_width"))
        return 1

    def apply_to(self, settings: Settings) -> None:
        settings.install_after_create = self.cb_install_auto.isChecked()
        settings.installer_restore = self.cb_install_restore.isChecked()
        settings.remember_window_position = self.rb_window_restore.isChecked()
        settings.startup_sound = self.cb_start_sound.isChecked()
        settings.select_game_mod = self.cb_select_game_mod.isChecked()
        settings.auto_character = self.cb_auto_character.isChecked()
        settings.copy_debug_mode_on_play = (
            _DEBUG_MODE_COMMAND if self.cb_copy_debug.isChecked() else ""
        )
        settings.copy_mod_name_on_play = self.cb_copy_mod_name.isChecked()
        settings.splitter_width = self._selected_splitter_width()
        settings.theme = self.theme_combo.currentData()

    def _on_apply(self) -> None:
        self.accept()

    def _on_advanced(self) -> None:
        # VB BtAdvanced: close (saving) and signal the caller to open full Settings.
        self.advanced_requested = True
        self.accept()

    @classmethod
    def edit(
        cls, settings_path=None, parent: QWidget | None = None
    ) -> tuple[Settings | None, bool]:
        """Show modally; persist on OK. Returns ``(settings|None, advanced_requested)``."""
        settings = load_settings(settings_path)
        dlg = cls(settings, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.apply_to(settings)
            save_settings(settings, settings_path)
            return settings, dlg.advanced_requested
        return None, False
