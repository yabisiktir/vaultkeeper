"""FileView — the grouped mod/contents pane, echoing the LazWorks ``FileView``.

The VB main form uses three ``LazWorks.Library.ListViews.FileView`` controls
(``FvMods``/``FvContents``/``FvDetails``) — a grouped list of file-backed rows with a
per-row state icon and state colouring. This widget reproduces the *visible* identity
of that control (group headers, a mod icon, the install-state icon and green/amber
state colour) on top of ``QTreeWidget``; the heavier FileView behaviours (drag-drop,
copy/paste, rich-text, custom-draw) are deferred.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

from vaultkeeper.core import constants as C
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.theme import status_colour


#: State colouring (VB FileView state colours). Resolved per call rather than
#: built once at import: the colour has to suit the palette in force, and a
#: module-level brush is fixed before any theme is applied.
def _installed_brush() -> QBrush:
    return QBrush(status_colour("installed"))


def _overridden_brush() -> QBrush:
    return QBrush(status_colour("overridden"))

#: Per-state row icon (maps the ModData mod_state to a bundled asset).
_STATE_ICON = {
    State.INSTALLED: "Installed",
    State.MATCH_OVERRIDE: "MatchOverride",
    State.INSTALLED_AND_OVERRIDDEN: "Overridden",
    State.OVERRIDDEN: "Overridden",
    State.NOT_INSTALLED: "NotInstalled",
}

_ROLE_MOD_NAME = 0x0100  # Qt.UserRole
_ROLE_GROUP_NAME = 0x0101  # Qt.UserRole + 1 (the row's group, for drag-to-group)
_ROLE_FILE_KEY = 0x0102  # Qt.UserRole + 2 (a Contents file's (folder, filename))


def icon_name_for_state(state: State) -> str:
    """The bundled asset name for a mod state (a folder for un-tracked states)."""
    return _STATE_ICON.get(state, "Folder_6221")


def file_state_brush(state: State) -> QBrush | None:
    """Row colour for a file's install state (green installed / amber overridden)."""
    if state in (State.OVERRIDDEN, State.INSTALLED_AND_OVERRIDDEN):
        return _overridden_brush()
    if state > State.NOT_INSTALLED:  # installed or match-override
        return _installed_brush()
    return None


class ContentsView(QTreeWidget):
    """The selected mod's files grouped by folder, with per-file install state.

    The VB Contents pane is another ``FileView`` (``FvContents``); this mirrors its
    visible identity — folder group rows, a per-file state icon and green/amber
    state colour — so the user can see which of a mod's files are installed.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Contents", "Size"])
        self.setRootIsDecorated(True)
        self.setColumnCount(2)
        header = self.header()
        header.setStretchLastSection(False)
        from PySide6.QtWidgets import QHeaderView

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

    def populate(self, report: dict) -> None:
        """Rebuild from a ``controller.mod_contents_report`` result."""
        from PySide6.QtCore import Qt

        self.clear()
        folder_icon = R.get_icon("Folder_6221")
        for group in report.get("folders", []):
            folder_item = QTreeWidgetItem([group["folder"], ""])
            folder_item.setIcon(0, folder_icon)
            folder_item.setFlags(folder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.addTopLevelItem(folder_item)
            for file in group["files"]:
                item = QTreeWidgetItem([file["name"], file["size_text"]])
                item.setIcon(0, R.get_icon(icon_name_for_state(file["state"])))
                item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight)
                # Carry the file's (folder, filename) so the pane can view/delete it.
                item.setData(0, _ROLE_FILE_KEY, (group["folder"], file["name"]))
                brush = file_state_brush(file["state"])
                if brush is not None:
                    item.setForeground(0, brush)
                folder_item.addChild(item)
            folder_item.setExpanded(True)

    def selected_file(self) -> tuple[str, str] | None:
        """The selected file's ``(folder, filename)``, or ``None`` for a group row."""
        item = self.currentItem()
        if item is None:
            return None
        return item.data(0, _ROLE_FILE_KEY)


class FileView(QTreeWidget):
    """A grouped, state-coloured mod list (echoes VB ``FvMods``)."""

    #: Emitted with the list of currently selected mod names.
    selection_changed = Signal(list)
    #: Emitted (mod_names, target_group) when mods are dragged onto a group.
    mods_dropped_on_group = Signal(list, str)
    #: Emitted when Return is pressed on a selected mod (macOS rename idiom).
    rename_requested = Signal()
    #: Emitted with a mod name when its *status icon* is clicked (VB newtopic28:
    #: "You can click a Mod's install status icon to Install or Uninstall").
    state_icon_clicked = Signal(str)

    def __init__(self, header: str = "Mods", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHeaderLabels([header])
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.setRootIsDecorated(True)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.itemClicked.connect(self._on_item_clicked)
        # Drag mods onto a group to move them (VB FileView drag-drop). The drop is
        # applied through the model (move_to_group) rather than Qt's default
        # re-parent, so the profile stays authoritative.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDropIndicatorShown(True)

    def _on_item_clicked(self, item, column: int) -> None:
        """Clicking the *icon* means install/uninstall; the label means select.

        The distinction has to be by x-position, because Qt reports a click on
        the icon and a click on the text as the same item click. Anything past
        the icon is an ordinary selection — otherwise picking a mod out of the
        list would install it, which is not a mistake anyone would forgive.
        """
        from PySide6.QtGui import QCursor

        name = item.data(0, _ROLE_MOD_NAME)
        if not name:
            return
        x = self.viewport().mapFromGlobal(QCursor.pos()).x()
        if self.is_over_icon(item, x):
            self.state_icon_clicked.emit(name)

    def is_over_icon(self, item, x: int) -> bool:
        """Whether ``x`` (viewport coordinates) is on the row's status icon.

        ``visualItemRect`` already accounts for the row's indentation, so its
        left edge is where the icon starts.
        """
        rect = self.visualItemRect(item)
        icon_width = self.iconSize().width() or 16
        return rect.left() <= x <= rect.left() + icon_width + 4

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        """Return renames the selected mod, the way Finder does.

        Deliberately handled here rather than as a shortcut on the Rename action:
        a window-wide ``Return`` shortcut is checked before the key ever reaches
        the focused widget, so it swallows Return in every text field in the
        window — including the inline editor this very command opens. Keeping it
        in the list means a focused editor gets its own Return, because the list
        is not what has focus then.
        """
        from PySide6.QtCore import Qt

        if (
            sys.platform == "darwin"
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers()
            and self.selected_mod_names()
        ):
            self.rename_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        from PySide6.QtCore import Qt

        names = self.selected_mod_names()
        target = self._group_at(event)
        if names and target is not None:
            self.mods_dropped_on_group.emit(names, target)
        # Applied through the model; suppress Qt's default re-parent (no super()).
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()

    def _group_at(self, event) -> str | None:
        """The group a drop lands in: the target row's group, else No Group."""
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        item = self.itemAt(pos)
        if item is None:
            return C.GROUP_NONE
        group = item.data(0, _ROLE_GROUP_NAME)
        return group if group is not None else C.GROUP_NONE

    # -- Population -------------------------------------------------------- #
    def populate(self, groups: list[tuple[str, list[ModData]]]) -> None:
        """Rebuild from ``(group_name, [ModData])`` rows (VB DisplayRoot).

        Groups whose key starts with the hidden-group prefix (``......`` — the
        "No Group" / "Installed" buckets) are not shown as a header row; their mods
        appear at the top level, matching the LazWorks FileView (GroupManager skips
        ``group.StartsWith(FileViewGroupHidden)``).
        """
        self.clear()
        group_icon = R.get_icon("Group")
        for group_name, members in groups:
            if group_name.startswith(C.GROUP_HIDDEN_PREFIX):
                for md in members:
                    self.addTopLevelItem(self._mod_item(md))
                continue
            group_item = QTreeWidgetItem([group_name])
            group_item.setIcon(0, group_icon)
            group_item.setData(0, _ROLE_GROUP_NAME, group_name)
            group_item.setFlags(group_item.flags() & ~self._selectable_flag())
            self.addTopLevelItem(group_item)
            for md in members:
                group_item.addChild(self._mod_item(md))
            group_item.setExpanded(True)

    def _mod_item(self, md: ModData) -> QTreeWidgetItem:
        label = f"{md.mod_name}  ✓" if md.installed else md.mod_name
        item = QTreeWidgetItem([label])
        item.setData(0, _ROLE_MOD_NAME, md.mod_name)
        item.setData(0, _ROLE_GROUP_NAME, md.group)
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
            return _overridden_brush()
        if md.installed:
            return _installed_brush()
        return None

    # -- Selection --------------------------------------------------------- #
    def selected_mod_names(self) -> list[str]:
        names: list[str] = []
        for item in self.selectedItems():
            name = item.data(0, _ROLE_MOD_NAME)
            if name:
                names.append(name)
        return names

    @staticmethod
    def mod_name_of(item) -> str:
        """The mod a row stands for, or "" for a group header."""
        return "" if item is None else (item.data(0, _ROLE_MOD_NAME) or "")

    def group_header_at(self, pos) -> str | None:
        """The group name if ``pos`` is over a (visible) group header, else None.

        Group headers carry a group name but no mod name and are not selectable,
        so group actions are offered via their right-click menu.
        """
        item = self.itemAt(pos)
        if item is None or item.data(0, _ROLE_MOD_NAME):
            return None
        return item.data(0, _ROLE_GROUP_NAME)

    def _mod_items(self):
        """Every mod row (top-level ungrouped rows + rows under group headers)."""
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            if top.childCount() == 0:
                yield top
            else:
                for j in range(top.childCount()):
                    yield top.child(j)

    def select_mod(self, mod_name: str) -> bool:
        """Select + scroll to a mod row by name (VB ``SelectMod``). True if found."""
        for item in self._mod_items():
            if item.data(0, _ROLE_MOD_NAME) == mod_name:
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return True
        return False

    def select_group(self, group_name: str) -> bool:
        """Expand + scroll to a group header, selecting its first mod (VB Go to Group)."""
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            # A group header has a group name but no mod name.
            if (
                item.data(0, _ROLE_MOD_NAME) is None
                and item.data(0, _ROLE_GROUP_NAME) == group_name
            ):
                item.setExpanded(True)
                self.scrollToItem(item)
                if item.childCount() > 0:
                    self.setCurrentItem(item.child(0))
                return True
        return False

    def _on_selection_changed(self) -> None:
        self.selection_changed.emit(self.selected_mod_names())

    @staticmethod
    def _selectable_flag():
        from PySide6.QtCore import Qt

        return Qt.ItemFlag.ItemIsSelectable
