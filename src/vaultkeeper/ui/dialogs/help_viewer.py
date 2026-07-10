"""HelpViewer — the in-app help window (VB CHM help displayed by ``HelpFileManager``).

Renders the bundled help topics (:mod:`vaultkeeper.ui.help_model`) in a QTextBrowser
with the table-of-contents tree beside it. Opened either at a specific topic (a
dialog's Help button → ``<ControlName>.htm``) or at the contents root (the Help menu).

QTextBrowser renders the HelpNDoc HTML and resolves the topics' relative image / css
references via its search path (the bundled help root), and follows in-page
``<topic>.htm`` links between topics.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import help_model as H


class HelpViewer(QDialog):
    """A contents tree + HTML topic viewer over the bundled help."""

    def __init__(self, topic: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Neverwinter Nights Installer Tool Help")
        self.resize(940, 640)

        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        self.contents = QTreeWidget()
        self.contents.setHeaderLabel("Contents")
        self.contents.setMinimumWidth(260)
        self.contents.itemSelectionChanged.connect(self._on_toc_select)
        splitter.addWidget(self.contents)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        # Resolve topics' relative img/css links against the help root.
        self.browser.setSearchPaths([str(H.help_root())])
        self.browser.anchorClicked.connect(self._on_anchor)
        splitter.addWidget(self.browser)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 660])

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._populate_toc()
        self.show_topic(topic or H.topic_for_control(H.DEFAULT_TOPIC))

    # -- Contents tree ---------------------------------------------------- #
    def _populate_toc(self) -> None:
        self.contents.clear()
        for node in H.load_toc():
            self.contents.addTopLevelItem(self._toc_item(node))
        self.contents.expandToDepth(0)

    def _toc_item(self, node: H.TocNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem([node.name])
        item.setData(0, Qt.ItemDataRole.UserRole, node.local)
        for child in node.children:
            item.addChild(self._toc_item(child))
        return item

    def _on_toc_select(self) -> None:
        items = self.contents.selectedItems()
        if not items:
            return
        local = items[0].data(0, Qt.ItemDataRole.UserRole)
        if local:
            path = H.topic_for_control(local)
            if path is not None:
                self._load(path)

    # -- Topic rendering -------------------------------------------------- #
    def show_topic(self, topic: Path | None) -> None:
        """Display a topic (falls back to a friendly message when unavailable)."""
        if topic is None or not topic.is_file():
            self.browser.setHtml(
                "<h2>Help topic unavailable</h2>"
                "<p>This help topic is not available.</p>"
            )
            return
        self._load(topic)
        self._select_toc_for(topic)

    def _load(self, path: Path) -> None:
        self.browser.setSource(QUrl.fromLocalFile(str(path)))

    def _on_anchor(self, url: QUrl) -> None:
        """Follow an in-help link (``<topic>.htm``) or ignore external ones."""
        name = url.fileName() or url.toString()
        target = H.topic_for_control(name)
        if target is not None:
            self._load(target)
            self._select_toc_for(target)

    def _select_toc_for(self, path: Path) -> None:
        """Highlight the TOC entry matching the shown topic, if present."""
        match = self._find_item(path.name.lower())
        if match is not None:
            self.contents.blockSignals(True)
            self.contents.setCurrentItem(match)
            self.contents.blockSignals(False)

    def _find_item(self, local_lower: str) -> QTreeWidgetItem | None:
        stack: list[QTreeWidgetItem] = [
            self.contents.topLevelItem(i)
            for i in range(self.contents.topLevelItemCount())
        ]
        while stack:
            item = stack.pop()
            local = item.data(0, Qt.ItemDataRole.UserRole) or ""
            if local.lower() == local_lower:
                return item
            stack.extend(item.child(i) for i in range(item.childCount()))
        return None

    # -- Entry points ----------------------------------------------------- #
    @classmethod
    def show_for_control(
        cls, control_name: str, parent: QWidget | None = None
    ) -> HelpViewer:
        """Open help at the topic for a VB control name (VB ``HelpFileManager.Open``)."""
        dlg = cls(H.topic_for_control(control_name), parent)
        dlg.show()
        return dlg

    @classmethod
    def show_contents(cls, parent: QWidget | None = None) -> HelpViewer:
        """Open help at the contents root (VB Help menu / TOC)."""
        dlg = cls(None, parent)
        dlg.show()
        return dlg


def help_button(control_name: str, parent: QWidget) -> QPushButton:
    """A dialog Help button opening the help topic for ``control_name`` (VB help button).

    Clicking it opens :class:`HelpViewer` at ``<control_name>.htm``, mirroring how each
    VB dialog's Help button calls ``HelpFileManager.Open(sender.Name)``. The opened
    viewer is stored on ``parent._help_viewer`` so it isn't garbage-collected.
    """
    button = QPushButton("Help")

    def _open() -> None:
        parent._help_viewer = HelpViewer.show_for_control(control_name, parent)

    button.clicked.connect(_open)
    return button
