"""FileView — the grouped mod/contents pane, echoing the LazWorks ``FileView``.

The VB main form uses three ``LazWorks.Library.ListViews.FileView`` controls
(``FvMods``/``FvContents``/``FvDetails``) — a grouped list of file-backed rows with a
per-row state icon and state colouring. This widget reproduces the *visible* identity
of that control (group headers, a mod icon, the install-state icon and green/amber
state colour) on top of ``QTreeWidget``; the heavier FileView behaviours (drag-drop,
copy/paste, rich-text, custom-draw) are deferred.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.ui import resources as R

#: State colouring (VB FileView state colours).
_INSTALLED_BRUSH = QBrush(QColor(0x2E, 0x7D, 0x32))  # green
_OVERRIDDEN_BRUSH = QBrush(QColor(0xB2, 0x6A, 0x00))  # amber

#: Per-state row icon (maps the ModData mod_state to a bundled asset).
_STATE_ICON = {
    State.INSTALLED: "Installed",
    State.MATCH_OVERRIDE: "MatchOverride",
    State.INSTALLED_AND_OVERRIDDEN: "Overridden",
    State.OVERRIDDEN: "Overridden",
    State.NOT_INSTALLED: "NotInstalled",
}

_ROLE_MOD_NAME = 0x0100  # Qt.UserRole


def icon_name_for_state(state: State) -> str:
    """The bundled asset name for a mod state (a folder for un-tracked states)."""
    return _STATE_ICON.get(state, "Folder_6221")


class FileView(QTreeWidget):
    """A grouped, state-coloured mod list (echoes VB ``FvMods``)."""

    #: Emitted with the list of currently selected mod names.
    selection_changed = Signal(list)

    def __init__(self, header: str = "Mods", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderLabels([header])
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.setRootIsDecorated(True)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    # -- Population -------------------------------------------------------- #
    def populate(self, groups: list[tuple[str, list[ModData]]]) -> None:
        """Rebuild from ``(group_name, [ModData])`` rows (VB DisplayRoot)."""
        self.clear()
        group_icon = R.get_icon("Group")
        for group_name, members in groups:
            group_item = QTreeWidgetItem([group_name])
            group_item.setIcon(0, group_icon)
            group_item.setFlags(group_item.flags() & ~self._selectable_flag())
            self.addTopLevelItem(group_item)
            for md in members:
                group_item.addChild(self._mod_item(md))
            group_item.setExpanded(True)

    def _mod_item(self, md: ModData) -> QTreeWidgetItem:
        label = f"{md.mod_name}  ✓" if md.installed else md.mod_name
        item = QTreeWidgetItem([label])
        item.setData(0, _ROLE_MOD_NAME, md.mod_name)
        item.setIcon(0, R.get_icon(self.state_icon_name(md)))
        brush = self.state_brush(md)
        if brush is not None:
            item.setForeground(0, brush)
        return item

    @staticmethod
    def state_icon_name(md: ModData) -> str:
        """The row's state icon name (a folder for un-tracked/no-state mods)."""
        return icon_name_for_state(md.mod_state)

    @staticmethod
    def state_brush(md: ModData) -> QBrush | None:
        if md.mod_state in (State.OVERRIDDEN, State.INSTALLED_AND_OVERRIDDEN):
            return _OVERRIDDEN_BRUSH
        if md.installed:
            return _INSTALLED_BRUSH
        return None

    # -- Selection --------------------------------------------------------- #
    def selected_mod_names(self) -> list[str]:
        names: list[str] = []
        for item in self.selectedItems():
            name = item.data(0, _ROLE_MOD_NAME)
            if name:
                names.append(name)
        return names

    def _on_selection_changed(self) -> None:
        self.selection_changed.emit(self.selected_mod_names())

    @staticmethod
    def _selectable_flag():
        from PySide6.QtCore import Qt

        return Qt.ItemFlag.ItemIsSelectable
