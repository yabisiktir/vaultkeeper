"""DocOrganiser — the Mod Documentation Organiser (VB ``DocOrganiser``).

Lists the documentation files (ReadMe, Walkthrough, etc.) NIT finds for the
selected mods, split into two panes mirroring the VB form: **Downloads Folder
Documents** (candidates under ``_Downloads``, including inside archives) and
**Contents Panel Documents** (docs already in the mod). Built on
``ProfileController.doc_organiser_report``.

Read-only. The VB *Copy* action that moves selected downloaded docs up into the
Contents panel — with its unique-name qualifiers, version-number stripping and
CRC dedupe (``DocOrganiser.DocInfo``/``ProcessDocs``) — is deferred; see the
handoff. Window title, headings and column come from ``DocOrganiser.Designer.vb``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
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


class DocOrganiser(QDialog):
    """A read-only two-pane view of a mod's documentation files."""

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
        panes.addLayout(self._pane_column("Downloads Folder Documents", self.downloads))
        panes.addLayout(self._pane_column("Contents Panel Documents", self.contents))

        self.summary = QLabel()
        layout.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self.refresh()

    @staticmethod
    def _make_pane() -> QTreeWidget:
        tree = QTreeWidget()
        # VB shows a single "Documents" column; we surface file / folder / size.
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
        report = self._controller.doc_organiser_report(self._mod_names)
        self.summary.setText(report["summary"])
        self._fill(self.downloads, report["downloads"])
        self._fill(self.contents, report["contents"])

    @staticmethod
    def _fill(tree: QTreeWidget, rows: list[dict]) -> None:
        tree.clear()
        for row in rows:
            tree.addTopLevelItem(
                QTreeWidgetItem([row["file"], row["folder"], row["size"]])
            )
        if tree.topLevelItemCount() > 0:
            tree.setCurrentItem(tree.topLevelItem(0))

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
