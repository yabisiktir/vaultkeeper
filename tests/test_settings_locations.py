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
        "Appearance",
        "Web Menu",
        "Run Menu",
        "Character / Save Viewer",
        "Locations",
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
        "Appearance",
        "Web Menu",
        "Run Menu",
        "Character / Save Viewer",
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
