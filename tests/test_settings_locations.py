"""Tests for the Settings Locations slice (controller report + Settings tab).

Covers the bounded VB Settings *Locations* page: surface the resolved install and
store paths as (group / location / path) rows and render them on a Locations tab in
the SettingsDialog when a controller is present.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.config.settings import Settings  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog  # noqa: E402


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    game_root = tmp_path / "steamapps" / "common" / "Neverwinter Nights"
    game_root.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
    )


# -- Controller report ---------------------------------------------------- #


def test_report_lists_real_paths(tmp_path):
    controller = _controller(tmp_path)
    report = controller.locations_report()
    by_loc = {r["location"]: r for r in report["rows"]}

    assert by_loc["Game Installation"]["path"] == str(
        tmp_path / "steamapps" / "common" / "Neverwinter Nights"
    )
    assert by_loc["Profile Mods"]["path"] == str(tmp_path / "Profiles" / "P")
    assert by_loc["Profile Store File"]["path"] == str(tmp_path / "Data" / "P.json")
    # Steam-shaped layout => workshop content path resolves.
    assert by_loc["Steam Workshop Content"]["path"].endswith("704450")
    assert by_loc["Game Installation"]["group"] == "Neverwinter Nights"
    assert by_loc["Profile Mods"]["group"] == "Vaultkeeper"


def test_report_blank_when_unset(tmp_path):
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    game_root = tmp_path / "GOG" / "Neverwinter Nights"  # not Steam
    game_root.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods, game_root=game_root
    )  # no store_path
    by_loc = {r["location"]: r for r in controller.locations_report()["rows"]}
    assert by_loc["Steam Workshop Content"]["path"] == ""  # non-Steam
    assert by_loc["Profile Store File"]["path"] == ""  # no store


# -- Dialog --------------------------------------------------------------- #


def test_dialog_has_locations_tab_with_controller(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = SettingsDialog(Settings(), controller=controller)
    qtbot.addWidget(dlg)

    tab_titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert tab_titles == [
        "General",
        "Behaviour",
        "Downloads",
        "Appearance",
        "Web Menu",
        "Run Menu",
        "Character / Save Viewer",
        "Locations",
        "Profiles",
    ]
    # The Locations tab now has editable game-path fields.
    assert dlg.game_install_edit is not None
    assert dlg.game_user_edit is not None


def test_locations_edit_persists_paths(qtbot, tmp_path):
    controller = _controller(tmp_path)
    settings = Settings()
    dlg = SettingsDialog(settings, controller=controller)
    qtbot.addWidget(dlg)
    dlg.game_install_edit.setText("/games/NWN-EE")
    dlg.game_user_edit.setText("/home/me/Documents/Neverwinter Nights")
    dlg.apply_to(settings)
    assert settings.nwn_path == "/games/NWN-EE"
    assert settings.game_user_path == "/home/me/Documents/Neverwinter Nights"


def test_dialog_omits_locations_tab_without_controller(qtbot):
    dlg = SettingsDialog(Settings())
    qtbot.addWidget(dlg)
    assert dlg.locations is None
    tab_titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert tab_titles == [
        "General",
        "Behaviour",
        "Downloads",
        "Appearance",
        "Web Menu",
        "Run Menu",
        "Character / Save Viewer",
        # Profiles is there with or without a controller: it reads the settings,
        # not the open profile.
        "Profiles",
    ]


def test_settings_dialog_start_tab(qtbot):
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    dlg = SettingsDialog(Settings(), start_tab="Behaviour")
    qtbot.addWidget(dlg)
    assert dlg.tabs.tabText(dlg.tabs.currentIndex()) == "Behaviour"
    # Unknown/blank tab names leave the default (first) tab selected.
    dlg2 = SettingsDialog(Settings(), start_tab="Nope")
    qtbot.addWidget(dlg2)
    assert dlg2.tabs.currentIndex() == 0


# -- the start-up sound file (VB Locations: "NIT Start-up Sound") --------------- #
def _sound_dialog(qtbot, tmp_path, configured: str = ""):
    from vaultkeeper.config.settings import Settings

    settings = Settings(startup_sound_path=configured)
    dlg = SettingsDialog(settings, controller=_controller(tmp_path))
    qtbot.addWidget(dlg)
    return dlg, settings


def test_the_locations_page_offers_a_start_up_sound(qtbot, tmp_path):
    dlg, _ = _sound_dialog(qtbot, tmp_path)
    assert dlg.startup_sound_edit is not None


def test_choosing_a_sound_saves_it(qtbot, tmp_path):
    sound = tmp_path / "fanfare.wav"
    sound.write_bytes(b"RIFF....WAVE")
    dlg, settings = _sound_dialog(qtbot, tmp_path)
    dlg.startup_sound_edit.setText(str(sound))
    dlg.apply_to(settings)
    assert settings.startup_sound_path == str(sound)


def test_a_path_to_nothing_is_refused_rather_than_saved(qtbot, tmp_path):
    """VB Settings.Locations:173 skips the value when the file does not exist."""
    sound = tmp_path / "real.wav"
    sound.write_bytes(b"RIFF")
    dlg, settings = _sound_dialog(qtbot, tmp_path, configured=str(sound))
    dlg.startup_sound_edit.setText(str(tmp_path / "gone.wav"))
    dlg.apply_to(settings)
    assert settings.startup_sound_path == str(sound)  # the good one survives


def test_clearing_it_means_use_the_games_own(qtbot, tmp_path):
    """Blank is a real answer — different from a wrong path, which is refused."""
    sound = tmp_path / "real.wav"
    sound.write_bytes(b"RIFF")
    dlg, settings = _sound_dialog(qtbot, tmp_path, configured=str(sound))
    dlg.startup_sound_edit.setText("   ")
    dlg.apply_to(settings)
    assert settings.startup_sound_path == ""


def test_the_placeholder_names_the_games_own_sound(qtbot, tmp_path):
    """So an empty box says what it will actually play, rather than nothing."""
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog as SD

    controller = _controller(tmp_path)
    game = controller.ctx.game_root / "data" / "mus"
    game.mkdir(parents=True, exist_ok=True)
    (game / "mus_autorun.wav").write_bytes(b"RIFF")
    assert SD._default_startup_sound(controller).endswith("mus_autorun.wav")


def test_no_game_sound_says_so_rather_than_naming_a_missing_file(qtbot, tmp_path):
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog as SD

    assert SD._default_startup_sound(_controller(tmp_path)) == ""
