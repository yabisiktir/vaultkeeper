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
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R

#: VB ``LbHeading.Text``.
_HEADING = (
    "Copy Mod information documents (ReadMe, Walkthrough, etc) from the Downloads "
    "folder to the Contents Panel for easier access."
)

#: Foreground for disabled items (VB ``DisabledItemColour``).
_DISABLED = QColor(0x80, 0x80, 0x80)


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
        # VB CmVersion/TsVersion toggle — strip version numbers from doc names.
        self.version_check = QCheckBox("Remove version numbers")
        self.version_check.setToolTip(
            "Remove version numbers from document names when copying."
        )
        self.version_check.toggled.connect(self.refresh)
        buttons.addWidget(self.version_check)
        buttons.addStretch(1)
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
        self._fill_contents(report["contents"])
        self._fill_downloads(report["downloads"])
        self._update_copy_button()

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
            # Only loose, unmatched docs can be copied (archive sources do not
            # survive the scan — deferred; matched docs already exist).
            copyable = bool(row["copy"]) and not row["from_archive"]
            if copyable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Checked)
            else:
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setDisabled(True)
                _italicise(item)
                for col in range(item.columnCount()):
                    item.setForeground(col, QBrush(_DISABLED))
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
        if current is None:
            return
        row = current.data(0, Qt.ItemDataRole.UserRole)
        if not row:
            return
        result = self._controller.doc_preview(row["source_path"])
        self.preview.setPlainText(result["text"])

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
            by_mod.setdefault(row["mod"], []).append(
                {"source": row["source_path"], "doc_name": row["doc_name"]}
            )

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
