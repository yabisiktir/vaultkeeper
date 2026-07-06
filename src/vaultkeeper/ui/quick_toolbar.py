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
        for item in QUICK_ITEMS:
            if item.action == "":
                self.addSeparator()
                continue
            act = self.addAction(R.get_icon(item.image), item.caption)
            act.setToolTip(item.caption)
            act.triggered.connect(
                lambda _=False, a=item.action: self.action_triggered.emit(a)
            )
            self.actions_by_id[item.action] = act

    def set_enabled(self, action: str, enabled: bool) -> None:
        """Enable/disable a toolbar button by VB control-name id."""
        act = self.actions_by_id.get(action)
        if act is not None:
            act.setEnabled(enabled)
