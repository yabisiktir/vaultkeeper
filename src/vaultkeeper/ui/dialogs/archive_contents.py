"""What is inside a compressed file (``reducefileclutter.htm``).

The topic's advice is to keep large archives compressed — *Move to Downloads*
puts them back — and it then promises you can still see inside them. Both halves
matter: this reads the archive index and unpacks nothing, so looking inside
CEP's 1.1 GB part costs about as much as opening a folder.

Each row also says which game folder that file would install to, because that is
the question a person opens an archive to answer. A blank means the tool has no
mapping for it — a readme, a screenshot, an installer's own leftovers.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R


class ArchiveContentsDialog(QDialog):
    """A read-only listing of an archive's members."""

    def __init__(
        self, name: str, entries: list[dict], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._entries = list(entries)

        self.setWindowTitle(f"Inside {name}")
        self.setWindowIcon(R.get_icon("ExtractMethod_6786"))
        geometry.remember(self, "ArchiveContentsDialog", 720, 480)

        layout = QVBoxLayout(self)
        total = sum(int(e.get("size", 0)) for e in self._entries)
        self.summary = QLabel(
            f"{len(self._entries):,} file(s), {total:,} bytes uncompressed. "
            "Nothing has been extracted."
        )
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        search = QHBoxLayout()
        search.addWidget(QLabel("Find:"))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("part of a file name")
        self.filter.textChanged.connect(self._on_filter)
        search.addWidget(self.filter, 1)
        layout.addLayout(search)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(["File", "Installs to", "Size"])
        self.table.setRootIsDecorated(False)
        self.table.setSortingEnabled(True)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._populate("")

    def _populate(self, needle: str) -> None:
        needle = needle.strip().lower()
        self.table.setSortingEnabled(False)
        self.table.clear()
        shown = 0
        for entry in self._entries:
            path = str(entry.get("path", ""))
            if needle and needle not in path.lower():
                continue
            row = QTreeWidgetItem(
                [path, str(entry.get("folder", "")), f"{int(entry.get('size', 0)):,}"]
            )
            self.table.addTopLevelItem(row)
            shown += 1
        self.table.setSortingEnabled(True)
        if needle:
            self.summary.setText(
                f"{shown:,} of {len(self._entries):,} file(s) match. "
                "Nothing has been extracted."
            )

    def _on_filter(self, text: str) -> None:
        if not text.strip():
            total = sum(int(e.get("size", 0)) for e in self._entries)
            self.summary.setText(
                f"{len(self._entries):,} file(s), {total:,} bytes uncompressed. "
                "Nothing has been extracted."
            )
        self._populate(text)

    @classmethod
    def show_for(
        cls, controller, path: Path, parent: QWidget | None = None
    ) -> ArchiveContentsDialog | None:
        """Open the listing for ``path``, or ``None`` if it cannot be read."""
        entries = controller.archive_listing(path)
        if entries is None:
            return None
        dlg = cls(path.name, entries, parent)
        dlg.show()
        return dlg
