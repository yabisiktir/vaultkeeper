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

    # The start-up sound (VB PlayStartupSound, from the Shown event). Held
    # deliberately on the window: QSoundEffect stops the moment it is collected,
    # so a local would play nothing at all.
    window.startup_sound = _play_startup_sound(settings, controller)

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


def _play_startup_sound(settings, controller):
    """Play the configured start-up sound; returns the player to keep it alive.

    Silent, and never fatal: a missing file, a machine with no audio device, or
    a PySide6 built without QtMultimedia all end the same way — no sound, no
    message, a line in the log. Holding Ctrl at start-up suppresses it, as VB
    does, which is the escape hatch when the fanfare is the last thing you want.
    """
    if not getattr(settings, "startup_sound", False):
        return None
    try:
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtMultimedia import QSoundEffect

        if QGuiApplication.queryKeyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            return None
        from vaultkeeper.game.startup_sound import resolve_sound

        game_root = getattr(getattr(controller, "ctx", None), "game_root", None)
        sound = resolve_sound(settings.startup_sound_path, game_root)
        if sound is None:
            logger.info("Start-up sound is on, but no sound file was found")
            return None
        effect = QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(str(sound)))
        effect.play()
        return effect
    except Exception:
        logger.exception("Could not play the start-up sound; continuing")
        return None
