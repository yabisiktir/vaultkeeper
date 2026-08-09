"""Tests for the start-up recovery options (VB command line + start-up keys).

These exist for one situation: the app will not start. So the tests care about
*ordering* — settings and restore must happen before anything reads the profile
— as much as about parsing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vaultkeeper import recovery
from vaultkeeper.startup_options import (
    OPTIONS,
    StartupOptions,
    from_modifiers,
    parse_args,
    usage_text,
)


def test_full_names_and_single_letters_both_work():
    assert parse_args(["-Settings"]).show_settings is True
    assert parse_args(["-S"]).show_settings is True
    assert parse_args(["-restoreprofiledata"]).restore_profile_data is True
    assert parse_args(["-r"]).restore_profile_data is True


def test_options_can_be_combined():
    options = parse_args(["-P", "-M"])
    assert options.validate_profile and options.music_off
    assert not options.show_settings


def test_every_abbreviation_is_unique():
    """The whole scheme rests on it: two options sharing an initial would make
    one of them unreachable by its documented short form."""
    initials = [name[0].lower() for name in OPTIONS]
    assert len(set(initials)) == len(initials)


def test_unknown_options_are_reported_not_dropped():
    """A typo that silently does nothing is how someone concludes the option
    does not work — VB shows them, so do we."""
    options = parse_args(["-Setings", "-S"])
    assert options.invalid == ["-Setings"]
    assert options.show_settings is True


def test_non_option_arguments_are_left_alone():
    assert parse_args(["some/file.vkmod"]).invalid == []


def test_held_keys_ask_for_the_same_things(qtbot):
    """The point of the keys: they work when there is no command line to type
    on, which is the case when someone double-clicks an icon."""
    from PySide6.QtCore import Qt

    assert from_modifiers(Qt.KeyboardModifier.ControlModifier).command_menu is True
    assert from_modifiers(Qt.KeyboardModifier.AltModifier).restore_profile_data is True
    assert from_modifiers(Qt.KeyboardModifier.ShiftModifier).music_off is True
    assert from_modifiers(Qt.KeyboardModifier.NoModifier).any_requested() is False


def test_a_key_and_a_flag_do_not_cancel_each_other_out():
    keys = StartupOptions(music_off=True)
    flags = parse_args(["-S"])
    both = flags.merged_with(keys)
    assert both.music_off and both.show_settings


def test_usage_lists_every_option():
    text = usage_text()
    for name in OPTIONS:
        assert f"-{name}" in text


# -- Restoring the store ------------------------------------------------------ #
def _store(tmp_path: Path) -> Path:
    (tmp_path / "Data").mkdir(parents=True)
    (tmp_path / "Backups").mkdir(parents=True)
    return tmp_path


def test_backups_are_listed_newest_first(tmp_path):
    import os
    import time

    root = _store(tmp_path)
    for index, name in enumerate(["P (pre-rebuild 1).json", "P (pre-rebuild 2).json"]):
        path = root / "Backups" / name
        path.write_text("{}")
        os.utime(path, (time.time() + index, time.time() + index))

    assert [p.name for p in recovery.data_backups(root)] == [
        "P (pre-rebuild 2).json",
        "P (pre-rebuild 1).json",
    ]


def test_a_missing_backups_folder_is_not_an_error(tmp_path):
    assert recovery.data_backups(tmp_path) == []


@pytest.mark.parametrize(
    ("filename", "profile"),
    [
        ("Main (pre-rebuild 2026-08-09 101500).json", "Main"),
        ("Main.json", "Main"),
        ("My Profile (pre-import 2026-01-01 000000).json", "My Profile"),
    ],
)
def test_the_profile_is_read_from_the_backup_name(filename, profile):
    assert recovery.profile_name_for(Path(filename)) == profile


def test_restoring_replaces_the_store_and_keeps_what_it_replaced(tmp_path):
    root = _store(tmp_path)
    target = root / "Data" / "Main.json"
    target.write_text(json.dumps({"which": "the broken one"}))
    backup = root / "Backups" / "Main (pre-rebuild 2026-08-09 101500).json"
    backup.write_text(json.dumps({"which": "the good one"}))

    message = recovery.restore_backup(backup, root)

    assert json.loads(target.read_text())["which"] == "the good one"
    kept = [p for p in (root / "Data").glob("Main (replaced *).json")]
    assert len(kept) == 1, "the file that was replaced is still there"
    assert json.loads(kept[0].read_text())["which"] == "the broken one"
    assert "Main" in message and kept[0].name in message


def test_restoring_into_a_profile_that_has_no_store_yet(tmp_path):
    root = _store(tmp_path)
    backup = root / "Backups" / "Fresh (pre-rebuild 1).json"
    backup.write_text("{}")

    recovery.restore_backup(backup, root)
    assert (root / "Data" / "Fresh.json").is_file()


# -- Where they take effect --------------------------------------------------- #
def test_the_recovery_steps_run_before_the_profile_is_loaded(qtbot, monkeypatch):
    """Ordering *is* the feature.

    Restoring the data or fixing the settings after the load has already crashed
    would be no use at all, so this asserts the sequence rather than the calls.
    """
    from vaultkeeper.ui import app as app_module

    order: list[str] = []
    monkeypatch.setattr(app_module, "_offer_data_restore", lambda: order.append("restore"))
    monkeypatch.setattr(
        app_module, "_show_settings_before_loading", lambda: order.append("settings")
    )
    monkeypatch.setattr(
        app_module,
        "_startup_options",
        lambda argv: StartupOptions(show_settings=True, restore_profile_data=True),
    )

    class _Window:
        startup_sound = None

        def __init__(self, controller):
            order.append("window")

        def show(self):
            pass

        def refresh(self):
            pass

    def _bootstrap():
        order.append("load profile")
        return None

    monkeypatch.setattr(app_module, "MainWindow", _Window)
    monkeypatch.setattr("vaultkeeper.ui.session.bootstrap_controller", _bootstrap)
    monkeypatch.setattr("vaultkeeper.ui.first_run.ask_first_run_choices", lambda: None)
    monkeypatch.setattr(
        "vaultkeeper.ui.session.auto_configure_first_run", lambda choices=None: None
    )
    monkeypatch.setattr(app_module.QApplication, "exec", lambda self: 0)

    app_module.run(argv=[])

    assert order.index("restore") < order.index("load profile")
    assert order.index("settings") < order.index("load profile")


def test_music_off_silences_the_startup_sound(qtbot):
    """It used to check Ctrl, which is VB's key for the options menu."""
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui import app as app_module

    settings = Settings()
    settings.startup_sound = True
    assert (
        app_module._play_startup_sound(settings, None, StartupOptions(music_off=True))
        is None
    )


def test_the_options_menu_offers_everything_except_itself(qtbot):
    from vaultkeeper.ui.dialogs.startup_options import StartupOptionsDialog

    dialog = StartupOptionsDialog()
    qtbot.addWidget(dialog)
    labels = [button.text() for _name, button in dialog._buttons]
    assert labels == [
        "Settings",
        "Profile Validate",
        "Restore Profile Data",
        "Music Off",
    ]
    # Choosing one turns that option on and leaves the rest alone.
    dialog._buttons[2][1].setChecked(True)
    assert dialog.chosen() == "RestoreProfileData"
    chosen = StartupOptions().with_option(dialog.chosen())
    assert chosen.restore_profile_data and not chosen.show_settings


def test_the_backup_list_shows_the_backups_newest_first(qtbot, tmp_path):
    import os
    import time

    from vaultkeeper.ui.dialogs.startup_options import DataBackupDialog

    root = _store(tmp_path)
    for index, name in enumerate(["Main (a).json", "Main (b).json"]):
        path = root / "Backups" / name
        path.write_text("{}")
        os.utime(path, (time.time() + index, time.time() + index))

    dialog = DataBackupDialog(recovery.data_backups(root))
    qtbot.addWidget(dialog)
    assert dialog.table.topLevelItem(0).text(0) == "Main (b).json"
    assert dialog.selected().name == "Main (b).json", "the newest is pre-selected"
