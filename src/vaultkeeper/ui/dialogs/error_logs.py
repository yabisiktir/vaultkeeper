"""NWN Error Log Information (VB ``BtHealth_Click`` ShowText).

The game writes AR_ERROR.LOG and logs/nwclienterror1.txt when something goes
wrong; the status bar's health icon shows while either has content. This shows
them, and Reset Log Files empties them so the icon means "new errors".
"""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ErrorLogsDialog(QDialog):
    def __init__(self, logs: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("NWN Error Log Information")
        self.resize(620, 440)
        self.reset_requested = False
        layout = QVBoxLayout(self)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        text.setPlainText("\n\n".join(f"{e['name']}:\n{e['text']}" for e in logs))
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        reset = QPushButton("Reset Log Files")
        reset.setToolTip("Clears the contents of the NWN error log files")
        buttons.addButton(reset, QDialogButtonBox.ButtonRole.ActionRole)
        reset.clicked.connect(self._on_reset)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_reset(self) -> None:
        self.reset_requested = True
        self.accept()
