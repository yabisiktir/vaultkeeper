"""QuickToolbar — the quick-access command strip, faithful to the VB ``TsQuick``.

Ported from ``NIT.Designer.vb``: an icon toolbar of the most-used commands, in the
original order with the original separators, images and captions. Each button uses
its VB control name (``TsInstall`` …) as its action id and clicking emits
:attr:`QuickToolbar.action_triggered` so the controller wires handlers 1:1 with VB.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QToolBar, QWidget

from vaultkeeper.ui import resources as R


@dataclass(frozen=True)
class ToolItem:
    """One quick-toolbar button (or a separator when ``action`` is empty)."""

    action: str
    image: str
    caption: str


#: A separator sentinel between button groups.
SEP = ToolItem("", "", "")

def items_from_settings(saved: list) -> tuple[ToolItem, ...]:
    """Turn the saved toolbar list back into items, falling back to the default.

    Each saved entry is ``{"action", "caption"}``; the image comes from the
    default definition for that command, because an icon is not something the
    editor lets anyone choose and not something worth storing per profile.
    """
    if not saved:
        return QUICK_ITEMS
    by_action = {i.action: i for i in QUICK_ITEMS if i.action}
    out: list[ToolItem] = []
    for entry in saved:
        action = str(entry.get("action", ""))
        if not action:
            out.append(SEP)
            continue
        default = by_action.get(action)
        image = str(entry.get("image", "")) or (default.image if default else "")
        caption = str(entry.get("caption", "")) or (default.caption if default else action)
        out.append(ToolItem(action, image, caption))
    return tuple(out)


def items_to_settings(items) -> list[dict]:
    """The saveable form of a toolbar list."""
    return [
        {"action": i.action, "image": i.image, "caption": i.caption} for i in items
    ]


#: The quick toolbar, verbatim from ``NIT.Designer.vb`` ``TsQuick.Items``.
QUICK_ITEMS: tuple[ToolItem, ...] = (
    ToolItem("TsSelectAll", "SelectAll", "Select All"),
    SEP,
    ToolItem("TsCut", "Cut-006", "Cut"),
    ToolItem("TsCopy", "CopyOffice2016", "Copy"),
    ToolItem("TsCopyName", "CopyName", "Name"),
    ToolItem("TsPaste", "PasteW10", "Paste"),
    SEP,
    ToolItem("TsDelete", "delete_16x16", "Delete"),
    ToolItem("TsRename", "RenameBlack", "Rename"),
    ToolItem("TsFind", "Search16", "Find"),
    SEP,
    ToolItem("TsNewGroup", "Group", "New Group"),
    ToolItem("TsNewMod", "EntityDataModel_entity_type_16x16", "New Mod"),
    ToolItem("TsMoveToGroup", "XSDSchema_GraphRightToLeft", "Move to"),
    ToolItem("TsGoToGroup", "Stepout_6327", "Go to"),
    SEP,
    ToolItem("TsDownloadProject", "DownloadProject_16x", "Project"),
    ToolItem("TsAddFiles", "MoveToFolderHS", "Add Files"),
    ToolItem("TsUpdateDownloads", "Downloads", "Downloads"),
    ToolItem("TsCreateInstaller", "FolderMapping16", "Installer"),
    SEP,
    ToolItem("TsInstall", "Install Package 16x16", "Install"),
    ToolItem("TsUninstall", "Uninstall", "Uninstall"),
    ToolItem("TsCreateRestorer", "Windows Seven Icon 63-003", "Restorer"),
    SEP,
    ToolItem("TsModExplorer", "Mod Explorer 1", "Explorer"),
    ToolItem("TsGameSaves", "GameManager16", "Saves"),
    ToolItem("TsPlayNeverwinterNights", "StatusRun_16x", "Play NWN"),
)


class QuickToolbar(QToolBar):
    """The main window quick-access toolbar (VB ``TsQuick``)."""

    #: Emitted with a button's VB control-name id when it is triggered.
    action_triggered = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Quick Access", parent)
        self.setIconSize(QSize(16, 16))
        self.setMovable(False)
        self.setFloatable(False)
        self.actions_by_id: dict[str, object] = {}
        self.populate(QUICK_ITEMS)

    def populate(self, items) -> None:
        """Rebuild the strip from ``items`` (VB's toolbar editor writes this list)."""
        self.clear()
        self.actions_by_id = {}
        for item in items:
            if item.action == "":
                self.addSeparator()
                continue
            act = self.addAction(R.get_icon(item.image), item.caption)
            act.setToolTip(item.caption)
            act.triggered.connect(
                lambda _=False, a=item.action: self.action_triggered.emit(a)
            )
            self.actions_by_id[item.action] = act

    def set_show_text(self, show: bool) -> None:
        """Icons with or without their captions (VB ``MsShowText``)."""
        from PySide6.QtCore import Qt

        self.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextUnderIcon
            if show
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )

    def set_enabled(self, action: str, enabled: bool) -> None:
        """Enable/disable a toolbar button by VB control-name id."""
        act = self.actions_by_id.get(action)
        if act is not None:
            act.setEnabled(enabled)

    def set_visible(self, action: str, visible: bool) -> None:
        """Show/hide a toolbar button by VB control-name id (VB ToolItem.Visible)."""
        act = self.actions_by_id.get(action)
        if act is not None:
            act.setVisible(visible)
