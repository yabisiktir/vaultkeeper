"""Qt application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def run(controller: ProfileController | None = None, argv: list[str] | None = None) -> int:
    """Create the QApplication, show the main window, and run the event loop."""
    app = QApplication.instance() or QApplication(argv or sys.argv)
    window = MainWindow(controller)
    window.show()
    return app.exec()
