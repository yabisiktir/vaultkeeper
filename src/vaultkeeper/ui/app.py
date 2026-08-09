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
    discovery; the window opens empty when nothing is configured yet. ``argv`` is
    the arguments *after* the program name, and carries the start-up recovery
    options (:mod:`vaultkeeper.startup_options`).
    """
    # Before the QApplication: macOS builds the Apple menu from the bundle name
    # the first time a menu bar appears, and run from source that name is the
    # interpreter's ("Python").
    from vaultkeeper.ui.mac_app_name import set_application_name

    set_application_name("Vaultkeeper")

    app = QApplication.instance() or QApplication(sys.argv[:1] + list(argv or []))
    options = _startup_options(argv)
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
            app,
            font_point_size=settings.font_point_size,
            theme=settings.theme,
            font_family=settings.font_family,
        )
    except Exception:
        logger.exception("Failed to apply saved appearance settings; continuing with defaults")

    # Everything the recovery options do, they do *before* the profile is read —
    # that is the whole point of them, and the reason this block cannot move
    # below the bootstrap (VB runs them from ProcessCommandLine, pre-load).
    if options.invalid:
        _report_invalid_options(options.invalid)
    if options.restore_profile_data:
        _offer_data_restore()
    if options.show_settings:
        _show_settings_before_loading()

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
        # Which kind of collection this is, before anything is built from it.
        window.offer_player_excludes()
        window.offer_legacy_import()

    # Validation runs after loading — it is the load's *result* it checks (VB
    # OnLoadValidateProfile, applied once the profile data is in).
    if options.validate_profile and controller is not None:
        try:
            window.nit_status.set_info(controller.validate_profile_data())
            window.refresh()
        except Exception:
            logger.exception("Profile validation failed; continuing")

    # The start-up sound (VB PlayStartupSound, from the Shown event). Held
    # deliberately on the window: QSoundEffect stops the moment it is collected,
    # so a local would play nothing at all.
    window.startup_sound = _play_startup_sound(settings, controller, options)

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


def _startup_options(argv):
    """What the command line and the held keys ask for, together.

    Reading the keyboard needs a QApplication, which is why this runs after one
    exists rather than in ``__main__``.
    """
    from PySide6.QtGui import QGuiApplication

    from vaultkeeper import startup_options as so

    options = so.parse_args(list(argv if argv is not None else sys.argv[1:]))
    options = options.merged_with(
        so.from_modifiers(QGuiApplication.queryKeyboardModifiers())
    )
    if options.command_menu:
        from vaultkeeper.ui.dialogs.startup_options import StartupOptionsDialog

        options = StartupOptionsDialog.choose(options)
    return options


def _report_invalid_options(invalid: list[str]) -> None:
    """Say which arguments were not understood, rather than dropping them."""
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.startup_options import usage_text

    box = QMessageBox(
        QMessageBox.Icon.Information,
        "Vaultkeeper",
        "These start-up options were not recognised:\n\n  "
        + "\n  ".join(invalid),
    )
    box.setDetailedText(usage_text())
    box.exec()


def _offer_data_restore() -> None:
    """List the profile-store backups and restore the chosen one (VB -R).

    Runs before any store is opened, because the store being unreadable is the
    reason to be here.
    """
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.app_paths import VaultStore
    from vaultkeeper.recovery import data_backups, restore_backup
    from vaultkeeper.ui.dialogs.startup_options import DataBackupDialog

    try:
        root = VaultStore.default().root
        backups = data_backups(root)
        if not backups:
            QMessageBox.information(
                None,
                "Restore Profile Data",
                f"There are no data backups in {root / 'Backups'} yet.",
            )
            return
        dialog = DataBackupDialog(backups)
        from PySide6.QtWidgets import QDialog

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dialog.selected()
        if chosen is not None:
            QMessageBox.information(
                None, "Restore Profile Data", restore_backup(chosen, root)
            )
    except Exception:
        logger.exception("Restoring profile data failed")


def _show_settings_before_loading() -> None:
    """Open Settings with no profile behind it (VB -S).

    Settings that point somewhere impossible are one of the two documented
    reasons the tool will not start, so this has to work with no controller.
    """
    try:
        from vaultkeeper.config.settings import load_settings
        from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

        # No controller: there is no profile yet, and getting to one is the
        # reason we are here. The dialog's first argument is the settings, not
        # the parent — passing None there crashed this path.
        SettingsDialog(load_settings(), None).exec()
    except Exception:
        logger.exception("Could not show settings before loading")


def _play_startup_sound(settings, controller, options=None):
    """Play the configured start-up sound; returns the player to keep it alive.

    Silent, and never fatal: a missing file, a machine with no audio device, or
    a PySide6 built without QtMultimedia all end the same way — no sound, no
    message, a line in the log. ``-MusicOff`` silences it, as does holding Shift
    at start-up — the escape hatch when the fanfare is the last thing you want.
    (This used to check Ctrl, which is VB's key for the options *menu*, not for
    the sound.)
    """
    if not getattr(settings, "startup_sound", False):
        return None
    if options is not None and options.music_off:
        return None
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QSoundEffect

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
