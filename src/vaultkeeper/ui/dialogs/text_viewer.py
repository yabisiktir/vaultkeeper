"""TextViewer — a read-only text/log file viewer (VB LazWorks ``ShowText``).

Used by the View menu's log/ini/config file items. Loads a file into a monospace
read-only editor with a title; shows a friendly placeholder when the file is
absent. Carries a Find button (Ctrl+F), as the original's viewer does.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import geometry
from vaultkeeper.ui import resources as R

_MAX_BYTES = 4_000_000  # guard against enormous logs


class TextViewer(QDialog):
    """A read-only viewer for a text or log file."""

    def __init__(self, path: Path | None, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(R.get_icon("NIT_Log_16x"))
        geometry.remember(self, "TextViewer", 720, 520)

        layout = QVBoxLayout(self)
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(QFont("Menlo", 11))
        self.editor.setPlainText(self._load(path))
        layout.addWidget(self.editor)

        # "Press the Find button, Ctrl+F or click Find from the Edit menu" —
        # a viewer you cannot search is not much use on a log.
        row = QHBoxLayout()
        row.addStretch(1)
        self._find_button = QPushButton("Find…")
        self._find_button.setShortcut(QKeySequence.StandardKey.Find)
        self._find_button.clicked.connect(self.open_find)
        row.addWidget(self._find_button)
        layout.addLayout(row)

    def open_find(self) -> None:
        """Open the Find bar on this viewer's text."""
        from vaultkeeper.ui.dialogs.find_text import FindTextDialog

        self.find_dialog = FindTextDialog(self.editor, self)
        self.find_dialog.show()

    @staticmethod
    def _load(path: Path | None) -> str:
        if path is None:
            return "(no file available)"
        if not path.is_file():
            return f"(file not found)\n\n{path}"
        try:
            data = path.read_bytes()[:_MAX_BYTES]
            return data.decode("utf-8", errors="replace")
        except OSError as ex:  # pragma: no cover - unusual I/O failure
            return f"(unable to read file)\n\n{path}\n{ex}"

    @classmethod
    def show_file(
        cls, path: Path | None, title: str, parent: QWidget | None = None
    ) -> TextViewer:
        dlg = cls(path, title, parent)
        dlg.show()
        return dlg

    @classmethod
    def show_text(
        cls, text: str, title: str, parent: QWidget | None = None
    ) -> TextViewer:
        """Show arbitrary report text (VB ``ShowText`` with an in-memory string)."""
        dlg = cls(None, title, parent)
        dlg.editor.setPlainText(text)
        dlg.show()
        return dlg
