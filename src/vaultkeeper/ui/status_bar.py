"""NitStatusBar — the main window status bar, faithful to the VB ``TsStatus``.

Ported from ``NIT.Designer.vb`` (the ``TsStatus`` StatusStrip) and ``NIT.StatusBar.vb``
(handlers/state). Reproduces the original segments, images, tooltips and left/right
layout:

* left:  ``Mods:`` selector, mod-count (``0/0``), ``Group:`` / group-name;
* centre: the info/message area (stretches);
* right: file-check, health, wizard, character, select-text-file, overwrite and
  recycle-toggle image buttons.

State-bearing images (recycle on/off, overwrite on/off, the select-file cycle) and
optional/conditional segments (health, wizard, file-check) are exposed through
setters and Qt signals so the controller drives them exactly like the VB handlers.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QStatusBar,
    QToolButton,
    QWidget,
)

from vaultkeeper.ui import resources as R

#: The select-text-file cycle states (VB SetSelectionPrefs).
SELECT_HISTORY = "history"
SELECT_PLAY_TIME = "play_time"
SELECT_TEXT_FILE = "text_file"

_SELECT_IMAGE = {
    SELECT_HISTORY: "SelectHistory",
    SELECT_PLAY_TIME: "SelectPlayTime",
    SELECT_TEXT_FILE: "SelectTextFileOn",
}
_SELECT_TOOLTIP = {
    SELECT_HISTORY: (
        "Selection History (Contents and Details items when the Mod was last selected)"
    ),
    SELECT_PLAY_TIME: "Play Time File",
    SELECT_TEXT_FILE: "Document File (rtf, txt, htm, html then pdf)",
}


class StatusIconButton(QToolButton):
    """A status-bar icon that reports right-clicks as well as clicks.

    Every one of these has a second, related screen behind the right button in
    the original — the Character Restorer icon opens the character summary, the
    Wizard icon opens the Wizard Builder, and so on. Qt gives no signal for it,
    and a behaviour with no signal is one nothing can wire.
    """

    right_clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.RightButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.right_clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


def _icon_button(image: str, tooltip: str) -> StatusIconButton:
    button = StatusIconButton()
    button.setAutoRaise(True)
    button.setIcon(R.get_icon(image))
    button.setIconSize(QSize(16, 16))
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _text_button(text: str, tooltip: str, *, bold: bool = False) -> QToolButton:
    button = QToolButton()
    button.setAutoRaise(True)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    button.setText(text)
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if bold:
        font = button.font()
        font.setBold(True)
        button.setFont(font)
    return button


class NitStatusBar(QStatusBar):
    """The main window status bar (VB ``TsStatus``)."""

    # Clicks mirror the VB ``Handles`` click handlers.
    mods_clicked = Signal()
    mod_count_clicked = Signal()
    group_clicked = Signal()
    info_clicked = Signal()
    file_check_clicked = Signal()
    health_clicked = Signal()
    wizard_clicked = Signal()
    character_clicked = Signal()
    character_right_clicked = Signal()
    wizard_right_clicked = Signal()
    select_file_right_clicked = Signal()
    recycle_right_clicked = Signal()
    select_file_clicked = Signal()
    overwrite_toggled = Signal(bool)
    recycle_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self._recycle = True
        self._overwrite = True
        self._select_state = SELECT_TEXT_FILE

        # -- Left cluster --------------------------------------------------- #
        self.bt_mods = _text_button("Mods:", "Click to show Recent Mods.", bold=False)
        self.bt_mod_count = _text_button("0/0", "", bold=True)
        self.bt_group_hdg = _text_button(
            "Group:", "Click to display Go to Group menu."
        )
        self.bt_group = _text_button("None", "", bold=True)

        # -- Centre message area ------------------------------------------- #
        self.mg_info = QLabel("")
        self.mg_info.setToolTip("Click to clear information message")
        self.mg_info.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mg_info.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        # -- Right cluster (icon buttons) ---------------------------------- #
        self.bt_file_check = _icon_button(
            "Information_16xLG_color",
            "Display details about files added, removed or changed\n"
            "in the NWN installation folder",
        )
        self.bt_health = _icon_button(
            "HealthWarningTriangle",
            "NWN error logs contain information.\nThere might be a potential issue.",
        )
        self.bt_wizard = _icon_button(
            "witchcraft",
            "Click to display the Create Installer Wizard Report.\n"
            "Right-Click to open the Wizard Builder.",
        )
        self.bt_character = _icon_button(
            "user", "Select Character Restorer associated with this Mod"
        )
        self.bt_select_file = _icon_button(
            _SELECT_IMAGE[self._select_state], _SELECT_TOOLTIP[self._select_state]
        )
        self.bt_overwrite = _icon_button("Overwrite", "Overwrite existing files")
        self.bt_recycle = _icon_button(
            "RecycleOn", "Deleted items are sent to the Recycle Bin / Trash"
        )

        self._build()
        self._wire()

        # Conditional segments are hidden until the controller reveals them.
        self.bt_file_check.hide()
        self.bt_health.hide()
        self.bt_wizard.hide()

    # -- Layout ------------------------------------------------------------ #
    def _build(self) -> None:
        for widget in (
            self.bt_mods,
            self.bt_mod_count,
            self.bt_group_hdg,
            self.bt_group,
        ):
            self.addWidget(widget)
        # The info label takes the remaining space (VB MgInfo "spring").
        self.addWidget(self.mg_info, 1)
        # Permanent widgets sit on the right; add left-to-right in visual order.
        for widget in (
            self.bt_file_check,
            self.bt_health,
            self.bt_wizard,
            self.bt_character,
            self.bt_select_file,
            self.bt_overwrite,
            self.bt_recycle,
        ):
            self.addPermanentWidget(widget)

    def _wire(self) -> None:
        self.bt_mods.clicked.connect(self.mods_clicked)
        self.bt_mod_count.clicked.connect(self.mod_count_clicked)
        self.bt_group_hdg.clicked.connect(self.group_clicked)
        self.bt_group.clicked.connect(self.group_clicked)
        self.bt_file_check.clicked.connect(self.file_check_clicked)
        self.bt_health.clicked.connect(self.health_clicked)
        self.bt_wizard.clicked.connect(self.wizard_clicked)
        self.bt_character.clicked.connect(self.character_clicked)
        # Right-click alternates (VB Bt*_MouseUp): each icon's second screen.
        self.bt_character.right_clicked.connect(self.character_right_clicked)
        self.bt_wizard.right_clicked.connect(self.wizard_right_clicked)
        self.bt_select_file.right_clicked.connect(self.select_file_right_clicked)
        self.bt_recycle.right_clicked.connect(self.recycle_right_clicked)
        self.bt_select_file.clicked.connect(self.select_file_clicked)
        self.bt_overwrite.clicked.connect(self._on_overwrite)
        self.bt_recycle.clicked.connect(self._on_recycle)

    # -- State setters (VB handlers) --------------------------------------- #
    def set_mod_count(self, installed: int, total: int) -> None:
        """Update the ``installed/total`` counter (VB BtModCount)."""
        self.bt_mod_count.setText(f"{installed}/{total}")

    def set_group(self, group_name: str) -> None:
        """Update the current-group label (VB BtGroup)."""
        self.bt_group.setText(group_name or "None")

    def set_info(self, text: str) -> None:
        """Set the info/message area text (VB MgInfo)."""
        self.mg_info.setText(text)

    def show_file_check(self, visible: bool) -> None:
        """Show/hide the pending-changes icon (VB ShowFileCheckIcon)."""
        self.bt_file_check.setVisible(visible)

    def show_health(self, visible: bool) -> None:
        self.bt_health.setVisible(visible)

    def show_wizard(self, visible: bool) -> None:
        self.bt_wizard.setVisible(visible)

    @property
    def recycle(self) -> bool:
        return self._recycle

    def set_recycle(self, on: bool) -> None:
        """Toggle recycle-vs-permanent delete (VB BtRecycleToggle)."""
        self._recycle = on
        self.bt_recycle.setIcon(R.get_icon("RecycleOn" if on else "RecycleOff"))
        self.bt_recycle.setToolTip(
            "Deleted items are sent to the Recycle Bin / Trash"
            if on
            else "Deleted items are permanently removed"
        )

    @property
    def overwrite(self) -> bool:
        return self._overwrite

    def set_overwrite(self, on: bool) -> None:
        """Toggle overwrite-existing-files (VB BtOverwrite)."""
        self._overwrite = on
        self.bt_overwrite.setIcon(R.get_icon("Overwrite" if on else "OverwriteOff"))

    @property
    def select_state(self) -> str:
        return self._select_state

    def set_select_state(self, state: str) -> None:
        """Set the select-text-file image/tooltip (VB SetSelectionPrefs)."""
        if state not in _SELECT_IMAGE:
            return
        self._select_state = state
        self.bt_select_file.setIcon(R.get_icon(_SELECT_IMAGE[state]))
        self.bt_select_file.setToolTip(_SELECT_TOOLTIP[state])

    # -- Internal toggles -------------------------------------------------- #
    def _on_overwrite(self) -> None:
        self.set_overwrite(not self._overwrite)
        self.overwrite_toggled.emit(self._overwrite)

    def _on_recycle(self) -> None:
        self.set_recycle(not self._recycle)
        self.recycle_toggled.emit(self._recycle)
