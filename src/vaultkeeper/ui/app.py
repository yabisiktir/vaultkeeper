"""Qt application bootstrap."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def run(controller: ProfileController | None = None, argv: list[str] | None = None) -> int:
    """Create the QApplication, show the main window, and run the event loop.

    If no controller is supplied, one is bootstrapped from saved settings + game
    discovery; the window opens empty when nothing is configured yet.
    """
    app = QApplication.instance() or QApplication(argv or sys.argv)
    # The taskbar and window switcher read the application's icon, not the
    # window's, so setting only the latter leaves a generic one there.
    app.setApplicationName("Vaultkeeper")
    app.setWindowIcon(R.app_icon())

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
            # First run. Two things go wrong in silence if nobody is asked —
            # which of several installations, and which drive the store lands
            # on — so ask, but only when there is genuinely a choice. Everything
            # else is auto-configured as before (VB auto-creates a profile
            # rather than dropping into an empty state).
            from vaultkeeper.ui.first_run import ask_first_run_choices

            choices = ask_first_run_choices()
            controller = auto_configure_first_run(choices=choices)
            first_run = controller is not None
    window = MainWindow(controller)
    window.show()
    if first_run:
        window.offer_legacy_import()

    # Auto-move Leto log files to the recycle bin on startup, when enabled (VB
    # DeleteLetoLogs, run from the Shown event). Best-effort: never block startup.
    if controller is not None:
        try:
            from vaultkeeper.config.settings import load_settings

            if load_settings().delete_leto_logs:
                removed = controller.remove_all_leto_log_files()
                if removed:
                    window.refresh()
                    window.nit_status.set_info(f"Removed {removed} Leto log file(s).")
        except Exception:
            logger.exception("Leto log auto-cleanup failed; continuing")

    return app.exec()
