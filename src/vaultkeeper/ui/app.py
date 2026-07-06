"""Qt application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def run(controller: ProfileController | None = None, argv: list[str] | None = None) -> int:
    """Create the QApplication, show the main window, and run the event loop.

    If no controller is supplied, one is bootstrapped from saved settings + game
    discovery; the window opens empty when nothing is configured yet.
    """
    app = QApplication.instance() or QApplication(argv or sys.argv)
    if controller is None:
        from vaultkeeper.ui.session import bootstrap_controller

        controller = bootstrap_controller()
    window = MainWindow(controller)
    window.show()
    return app.exec()
