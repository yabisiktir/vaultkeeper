"""DocOrganiser — the Mod Documentation Organiser (VB ``DocOrganiser``).

Lists the documentation files (ReadMe, Walkthrough, etc.) NIT finds for the
selected mods, split into two panes mirroring the VB form: **Downloads Folder
Documents** (candidates under ``_Downloads``, including inside archives) and
**Contents Panel Documents** (docs already in the mod). Built on
``ProfileController.doc_organiser_report``.

The **Copy** button (VB ``BtCopy``) copies the checked Downloads docs up into the
mod root under their qualified ``DocName``. Downloads items are checkable and
default to the report's ``copy`` flag; a doc that already exists in Contents (CRC
match / ``name_match``) is shown disabled + italic and cannot be copied (VB
``DisabledItemColour`` + ``ItemCheck``), and archive-extracted docs are likewise
disabled — copying those is deferred (their source does not survive the scan).
Window title, headings and column come from ``DocOrganiser.Designer.vb``.

**Rename** / **Rename To** (VB ``CmRename`` / ``CmRenameTo``) change the name a
download will be copied as: Rename opens a name editor validated by
:func:`vaultkeeper.core.name_edit.validate_name`, and Rename To offers the matching
Contents doc names to reuse. A renamed doc is marked to copy.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.core.name_edit import validate_name
from vaultkeeper.ui import resources as R
from vaultkeeper.ui.theme import status_colour

#: VB ``LbHeading.Text``.
_HEADING = (
    "Copy Mod information documents (ReadMe, Walkthrough, etc) from the Downloads "
    "folder to the Contents Panel for easier access."
)

#: Foreground for disabled items (VB ``DisabledItemColour``).
def _disabled_colour() -> QColor:
    return status_colour("disabled")


class DocOrganiser(QDialog):
    """A two-pane view of a mod's documentation files with a Copy action."""

    def __init__(
        self,
        controller,
        mod_names: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._pending_preview = ""
        self._mod_names = mod_names
        self.setWindowTitle("Mod Documentation Organiser")
        self.setWindowIcon(R.get_icon("VBExtension_16x"))
        self.resize(820, 560)

        layout = QVBoxLayout(self)
        heading = QLabel(_HEADING)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        panes = QHBoxLayout()
        layout.addLayout(panes, 1)

        self.downloads = self._make_pane()
        self.contents = self._make_pane()
        for pane in (self.downloads, self.contents):
            pane.customContextMenuRequested.connect(self._on_context_menu)
        self.downloads.itemChanged.connect(self._on_item_changed)
        self.downloads.currentItemChanged.connect(self._on_selection)
        self.contents.currentItemChanged.connect(self._on_selection)
        panes.addLayout(self._pane_column("Downloads Folder Documents", self.downloads))
        panes.addLayout(self._pane_column("Contents Panel Documents", self.contents))

        # Read-only preview of the selected document (VB RtfDoc/RtfContents).
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select a document to preview it.")
        layout.addWidget(self.preview, 1)

        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        buttons.addWidget(help_button("BhDocManager", self))
        # VB CmVersion/TsVersion toggle — strip version numbers from doc names.
        self.version_check = QCheckBox("Remove version numbers")
        self.version_check.setToolTip(
            "Remove version numbers from document names when copying."
        )
        self.version_check.toggled.connect(self.refresh)
        buttons.addWidget(self.version_check)
        # VB CmRename / CmRenameTo — rename a download doc's copy target.
        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self._on_rename)
        buttons.addWidget(self.rename_button)
        self.rename_to_button = QToolButton()
        self.rename_to_button.setText("Rename To")
        self.rename_to_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.rename_to_menu = QMenu(self.rename_to_button)
        self.rename_to_button.setMenu(self.rename_to_menu)
        buttons.addWidget(self.rename_to_button)
        buttons.addStretch(1)
        self.read_button = QPushButton("Read Document")
        self.read_button.setToolTip("Extract this document from its archive and show it")
        self.read_button.setEnabled(False)
        self.read_button.clicked.connect(self._on_read_document)
        buttons.addWidget(self.read_button)
        self.properties_button = QPushButton("Properties")
        self.properties_button.setIcon(R.get_icon("PropertiesW10"))
        self.properties_button.setToolTip("Show the selected document's file details")
        self.properties_button.clicked.connect(self._on_properties)
        buttons.addWidget(self.properties_button)
        self.uncheck_button = QPushButton("Uncheck All")
        self.uncheck_button.clicked.connect(self._on_uncheck_all)
        buttons.addWidget(self.uncheck_button)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self._on_copy)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.refresh()

    @staticmethod
    def _make_pane() -> QTreeWidget:
        tree = QTreeWidget()
        # VB shows a single "Documents" column; we surface name / folder / size.
        tree.setHeaderLabels(["Document", "Folder", "Size"])
        tree.setRootIsDecorated(False)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        return tree

    @staticmethod
    def _pane_column(heading: str, tree: QTreeWidget) -> QVBoxLayout:
        column = QVBoxLayout()
        column.addWidget(QLabel(heading))
        column.addWidget(tree, 1)
        return column

    def refresh(self) -> None:
        """(Re)build both document lists from disk."""
        report = self._controller.doc_organiser_report(
            self._mod_names, remove_version=self.version_check.isChecked()
        )
        self.summary.setText(report["summary"])
        self._contents_rows = report["contents"]
        self._fill_contents(report["contents"])
        self._fill_downloads(report["downloads"])
        self._update_copy_button()
        self._sync_rename_buttons()

    def _fill_contents(self, rows: list[dict]) -> None:
        tree = self.contents
        tree.clear()
        for row in rows:
            item = QTreeWidgetItem([row["doc_name"], row["folder"], row["size"]])
            item.setData(0, Qt.ItemDataRole.UserRole, row)
            if row["name_match"]:
                # Matched by a downloaded doc — italicised (VB itemFont).
                _italicise(item)
            tree.addTopLevelItem(item)
        if tree.topLevelItemCount() > 0:
            tree.setCurrentItem(tree.topLevelItem(0))

    def _fill_downloads(self, rows: list[dict]) -> None:
        tree = self.downloads
        tree.blockSignals(True)
        tree.clear()
        for row in rows:
            item = QTreeWidgetItem([row["doc_name"], row["folder"], row["size"]])
            item.setData(0, Qt.ItemDataRole.UserRole, row)
            # Unmatched docs are copyable — loose files directly, and archive docs
            # by re-extraction (matched docs already exist in Contents).
            archive_copyable = row["from_archive"] and bool(row.get("archive"))
            copyable = bool(row["copy"]) and (not row["from_archive"] or archive_copyable)
            if copyable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked)
            else:
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setDisabled(True)
                _italicise(item)
                for col in range(item.columnCount()):
                    item.setForeground(col, QBrush(_disabled_colour()))
            tree.addTopLevelItem(item)
        tree.blockSignals(False)
        if tree.topLevelItemCount() > 0:
            tree.setCurrentItem(tree.topLevelItem(0))

    def _on_item_changed(self, _item: QTreeWidgetItem, _col: int) -> None:
        self._update_copy_button()

    def _on_selection(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        """Preview the newly selected document (VB DisplayFile)."""
        self._sync_rename_buttons()
        if current is None:
            return
        row = current.data(0, Qt.ItemDataRole.UserRole)
        if not row:
            return
        # A doc inside an archive is not on disk: the scan describes it from the
        # archive's index, so reading it means extracting it. That can take
        # seconds on a solid archive, which is far too long to spend on merely
        # moving the selection — so it is offered, not done.
        self._pending_preview = ""
        if row.get("from_archive") and not Path(row["source_path"]).is_file():
            self._pending_preview = row["source_path"]
            self.preview.setPlainText(
                f"{row['file']} is inside {row.get('archive') or 'an archive'}.\n\n"
                "Press Read Document to extract and show it."
            )
            self.read_button.setEnabled(True)
            return
        self.read_button.setEnabled(False)
        result = self._controller.doc_preview(row["source_path"])
        self.preview.setPlainText(result["text"])

    def _on_read_document(self) -> None:
        """Extract and show the selected archive doc (VB opens it directly)."""
        if not self._pending_preview:
            return
        from PySide6.QtWidgets import QApplication

        self.read_button.setEnabled(False)
        self.preview.setPlainText("Extracting…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            result = self._controller.doc_preview(self._pending_preview)
        finally:
            QApplication.restoreOverrideCursor()
        self.preview.setPlainText(
            result["text"] or "This document could not be read from the archive."
        )

    # -- Rename (VB CmRename / CmRenameTo) -------------------------------- #
    def _download_names(self) -> list[str]:
        """Every current Downloads doc name (for duplicate detection)."""
        return [
            self.downloads.topLevelItem(i)
            .data(0, Qt.ItemDataRole.UserRole)["doc_name"]
            for i in range(self.downloads.topLevelItemCount())
        ]

    def _sync_rename_buttons(self) -> None:
        item = self.downloads.currentItem()
        self.rename_button.setEnabled(item is not None)
        suggestions = self._rename_suggestions(item) if item is not None else []
        self.rename_to_menu.clear()
        for name in suggestions:
            self.rename_to_menu.addAction(name, lambda n=name: self._rename_to(n))
        self.rename_to_button.setEnabled(bool(suggestions))

    def _rename_suggestions(self, item: QTreeWidgetItem) -> list[str]:
        """Content doc names a download can be renamed to (VB ``SetRenameTo``).

        Existing Contents docs with no download match and the same extension, whose
        name isn't already used by a Downloads item.
        """
        row = item.data(0, Qt.ItemDataRole.UserRole)
        ext = PurePosixPath(row["doc_name"]).suffix.lower()
        used = {name.lower() for name in self._download_names()}
        suggestions: list[str] = []
        for content in getattr(self, "_contents_rows", []):
            if content.get("name_match"):
                continue
            doc_name = content["doc_name"]
            if PurePosixPath(doc_name).suffix.lower() != ext:
                continue
            if doc_name.lower() in used:
                continue
            suggestions.append(doc_name)
        return suggestions

    def _apply_rename(self, item: QTreeWidgetItem, new_name: str):
        """Validate + apply a new copy-target name (VB ``ValidateName`` + rename)."""
        row = item.data(0, Qt.ItemDataRole.UserRole)
        result = validate_name(
            new_name,
            initial=row["doc_name"],
            existing=self._download_names(),
            name_type="Document",
        )
        if not result.ok:
            return result
        new_row = dict(row)
        new_row["doc_name"] = new_name
        item.setData(0, Qt.ItemDataRole.UserRole, new_row)
        item.setText(0, new_name)
        # A renamed doc is marked for copying (VB checks the item).
        if (item.flags() & Qt.ItemFlag.ItemIsUserCheckable) and item.checkState(
            0
        ) != Qt.CheckState.Checked:
            item.setCheckState(0, Qt.CheckState.Checked)
        self._update_copy_button()
        self._sync_rename_buttons()
        return result

    def _on_rename(self) -> None:
        item = self.downloads.currentItem()
        if item is None:
            return
        row = item.data(0, Qt.ItemDataRole.UserRole)
        new_name, ok = QInputDialog.getText(
            self, "Rename Document", "Document name:", text=row["doc_name"]
        )
        if not ok:
            return
        result = self._apply_rename(item, new_name)
        if not result.ok:
            QMessageBox.warning(self, "Rename Document", result.message)

    def _rename_to(self, name: str) -> None:
        item = self.downloads.currentItem()
        if item is not None:
            self._apply_rename(item, name)

    def _checked_rows(self) -> list[dict]:
        rows: list[dict] = []
        for i in range(self.downloads.topLevelItemCount()):
            item = self.downloads.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                rows.append(item.data(0, Qt.ItemDataRole.UserRole))
        return rows

    def _update_copy_button(self) -> None:
        self.copy_button.setEnabled(len(self._checked_rows()) > 0)

    def _on_uncheck_all(self) -> None:
        """Uncheck every checkable Downloads doc (VB ``TsUncheck_Click``)."""
        for i in range(self.downloads.topLevelItemCount()):
            item = self.downloads.topLevelItem(i)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(0, Qt.CheckState.Unchecked)
        self._update_copy_button()

    def _on_copy(self) -> None:
        """Copy the checked Downloads docs into their mods (VB ``BtCopy_Click``)."""
        by_mod: dict[str, list[dict]] = {}
        for row in self._checked_rows():
            sel = {"doc_name": row["doc_name"]}
            if row.get("archive"):
                sel["archive"] = row["archive"]
                sel["inner"] = row["inner"]
            else:
                sel["source"] = row["source_path"]
            by_mod.setdefault(row["mod"], []).append(sel)

        copied = errors = 0
        for mod_name, selections in by_mod.items():
            result = self._controller.copy_docs_to_mod(mod_name, selections)
            copied += result["copied"]
            errors += result["errors"]

        self.refresh()
        parts = [f"Documents copied: {copied or 'None'}."]
        if errors:
            parts.append(f"Errors: {errors}.")
        self.summary.setText(" ".join(parts) + " " + self.summary.text())

    # -- Properties (VB CmProperties / TsProperties) ----------------------- #
    def _selected_row(self) -> dict | None:
        """The focused pane's selected row — VB reads whichever list has focus."""
        for tree in (self.downloads, self.contents):
            if tree.hasFocus():
                item = tree.currentItem()
                if item is not None:
                    return item.data(0, Qt.ItemDataRole.UserRole)
        for tree in (self.downloads, self.contents):
            item = tree.currentItem()
            if item is not None:
                return item.data(0, Qt.ItemDataRole.UserRole)
        return None

    def _on_properties(self) -> None:
        """Show the selected document's details.

        VB opens the Windows shell properties dialog. There is no cross-platform
        equivalent, so this shows the same facts itself — which also lets it say
        the things the shell could not know, like whether the document came out
        of an archive or already matches one in the mod.
        """
        row = self._selected_row()
        if row is None:
            return
        lines = [
            f"Name: {row.get('doc_name') or row.get('file', '')}",
            f"File: {row.get('file', '')}",
            f"Mod: {row.get('mod', '')}",
            f"Folder: {row.get('folder') or '(mod root)'}",
            # The report already formats this for the Size column, so it is a
            # string here — formatting it as a number raises.
            f"Size: {row.get('size', '')}",
        ]
        if row.get("from_archive"):
            lines.append(f"Inside archive: {row.get('archive', '')}")
            lines.append(f"Entry: {row.get('inner', '')}")
        elif row.get("source_path"):
            lines.append(f"Path: {row['source_path']}")
        if row.get("name_match"):
            lines.append("Already present in this mod (matching document found).")

        box = QMessageBox(self)
        box.setWindowTitle("Document Properties")
        box.setText(row.get("doc_name") or row.get("file", "Document"))
        box.setInformativeText("\n".join(lines))
        box.exec()

    def _on_context_menu(self, point) -> None:
        """The row actions, as VB offers them from CmDocs."""
        from PySide6.QtGui import QCursor

        sender = self.sender()
        menu = QMenu(self)
        for button, icon in (
            (self.rename_button, "RenameBlack"),
            (self.properties_button, "PropertiesW10"),
        ):
            action = menu.addAction(R.get_icon(icon), button.text().rstrip("…"))
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
        menu.addSeparator()
        reset = menu.addAction(R.get_icon("Reset_16x"), "Reset")
        reset.setToolTip("Re-scan, discarding the renames and checks you have made")
        reset.triggered.connect(self.refresh)
        menu.exec(sender.viewport().mapToGlobal(point) if sender is not None else QCursor.pos())

    @classmethod
    def show_for(
        cls,
        controller,
        mod_names: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> DocOrganiser:
        """Build and show the organiser for a controller's doc report."""
        dlg = cls(controller, mod_names, parent)
        dlg.show()
        return dlg


def _italicise(item: QTreeWidgetItem) -> None:
    for col in range(item.columnCount()):
        font = item.font(col)
        font.setItalic(True)
        item.setFont(col, font)
