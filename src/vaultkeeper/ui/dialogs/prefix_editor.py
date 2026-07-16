"""PrefixEditor — edit the Start-Screen prefix list (VB ``MsEditStartScreenPrefixes``).

The original opens ``LoadscreenPrefixes.txt`` in a text editor. This is the in-app
equivalent: a plain-text editor for that file. A prefix groups start-screen images by
the text before the first space in their file name; a line beginning with ``!`` keeps a
prefix defined but disabled (VB ``InactivePrefix``). Built on
``ProfileController.loadscreen_prefix_text`` / ``save_loadscreen_prefixes``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vaultkeeper.ui import resources as R


class PrefixEditor(QDialog):
    """Edit the Start-Screen prefix list."""

    def __init__(self, controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Edit Start Screen Prefixes")
        self.setWindowIcon(R.get_icon("Edit_16x"))
        self.resize(460, 420)

        outer = QVBoxLayout(self)
        help_text = QLabel(
            "One prefix per line. A prefix groups start-screen images by the text before "
            "the first space in their file name. Begin a line with '!' to keep a prefix "
            "defined but disabled."
        )
        help_text.setWordWrap(True)
        outer.addWidget(help_text)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(controller.loadscreen_prefix_text())
        outer.addWidget(self.editor, 1)

        buttons = QHBoxLayout()
        from vaultkeeper.ui.dialogs.help_viewer import help_button

        # VB opened LoadscreenPrefixes.txt in a text editor (no help button); the
        # port's dialog points at the Start Screen Manager topic (rbloadscreenhelp.htm).
        buttons.addWidget(help_button("RbLoadscreenHelp", self))
        buttons.addStretch(1)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(self.save_button)
        buttons.addWidget(close_button)
        outer.addLayout(buttons)

    def _on_save(self) -> None:
        self._controller.save_loadscreen_prefixes(self.editor.toPlainText())
        QMessageBox.information(self, "Edit Start Screen Prefixes", "Prefixes saved.")
        self.accept()

    @classmethod
    def show_for(cls, controller, parent: QWidget | None = None) -> PrefixEditor:
        """Build and show the prefix editor for a controller's profile."""
        dlg = cls(controller, parent)
        dlg.show()
        return dlg
