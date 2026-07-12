"""Qt application bootstrap."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def run(controller: ProfileController | None = None, argv: list[str] | None = None) -> int:
    """Create the QApplication, show the main window, and run the event loop.

    If no controller is supplied, one is bootstrapped from saved settings + game
    discovery; the window opens empty when nothing is configured yet.
    """
    app = QApplication.instance() or QApplication(argv or sys.argv)

    # Apply the persisted font size + theme (VB Restart()-after-FontAndColour
    # step). Best-effort: theming must never block startup.
    try:
        from vaultkeeper.config.settings import load_settings
        from vaultkeeper.ui.theme import apply_appearance

        settings = load_settings()
        apply_appearance(
            app, font_point_size=settings.font_point_size, theme=settings.theme
        )
    except Exception:
        logger.exception("Failed to apply saved appearance settings; continuing with defaults")

    first_run = False
    if controller is None:
        from vaultkeeper.ui.session import (
            auto_configure_first_run,
            bootstrap_controller,
        )

        controller = bootstrap_controller()
        if controller is None:
            # First run: establish a default profile from the discovered install
            # (VB auto-creates one) instead of dropping into an empty state.
            controller = auto_configure_first_run()
            first_run = controller is not None
    window = MainWindow(controller)
    window.show()
    if first_run:
        window.offer_legacy_import()
    return app.exec()
