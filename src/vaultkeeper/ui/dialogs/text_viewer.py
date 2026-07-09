"""TextViewer — a read-only text/log file viewer (VB LazWorks ``ShowText``).

Used by the View menu's log/ini/config file items. Loads a file into a monospace
read-only editor with a title; shows a friendly placeholder when the file is absent.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout, QWidget

from vaultkeeper.ui import resources as R

_MAX_BYTES = 4_000_000  # guard against enormous logs


class TextViewer(QDialog):
    """A read-only viewer for a text or log file."""

    def __init__(self, path: Path | None, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(R.get_icon("NIT_Log_16x"))
        self.resize(720, 520)

        layout = QVBoxLayout(self)
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(QFont("Menlo", 11))
        self.editor.setPlainText(self._load(path))
        layout.addWidget(self.editor)

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
