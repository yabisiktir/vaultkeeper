"""Move to Development (VB MsMoveToDev, newtopic55.htm / newtopic68.htm).

The Enhanced Edition ``development`` folder is opt-in: enabled from the Debug
Options menu, it lets a hot-fix be applied to override files while playing. The
documented path is to right-click an override file and choose *Move to
Development*; the same command brings it back to its primary folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def _make_controller(tmp_path: Path, *, development_folder: bool) -> ProfileController:
    payload = tmp_path / "Profiles" / "P" / "Aielund" / ".Mod Installer"
    (payload / "override").mkdir(parents=True)
    (payload / "override" / "hotfix.utc").write_bytes(b"FIX")
    (payload / "hak").mkdir()
    (payload / "hak" / "pack.hak").write_bytes(b"HAK")
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        development_folder=development_folder,
    )


@pytest.fixture()
def dev_controller(tmp_path: Path) -> ProfileController:
    return _make_controller(tmp_path, development_folder=True)


def _files(controller: ProfileController) -> set[tuple[str, str]]:
    md = controller.pd.mod_item("Aielund")
    return {(fk.folder, fk.filename) for fk in md.files}


# -- Controller gate + move -------------------------------------------------- #


def test_dev_move_target_is_none_when_the_folder_is_disabled(tmp_path):
    off = _make_controller(tmp_path, development_folder=False)
    assert off.dev_move_target("Aielund", "override", "hotfix.utc") is None


def test_override_file_moves_to_development_and_offers_the_trip_back(dev_controller):
    c = dev_controller
    assert c.dev_move_target("Aielund", "override", "hotfix.utc") == (
        "development",
        "Move to Development",
    )
    result = c.move_mod_files("Aielund", "override", ["hotfix.utc"], "development")
    assert result["ok"] and result["moved"] == 1

    payload = c.ctx.profile_mods_dir / "Aielund" / ".Mod Installer"
    assert (payload / "development" / "hotfix.utc").read_bytes() == b"FIX"
    assert ("development", "hotfix.utc") in _files(c)
    assert ("override", "hotfix.utc") not in _files(c)
    # A file already in development is offered the trip back to its primary.
    assert c.dev_move_target("Aielund", "development", "hotfix.utc") == (
        "override",
        "Move to Override",
    )


def test_a_hak_qualifies_but_a_non_override_file_does_not(dev_controller):
    c = dev_controller
    assert c.dev_move_target("Aielund", "hak", "pack.hak") == (
        "development",
        "Move to Development",
    )
    payload = c.ctx.profile_mods_dir / "Aielund" / ".Mod Installer"
    (payload / "modules").mkdir()
    (payload / "modules" / "camp.mod").write_bytes(b"M")
    c.pd.scan_mods(c.ctx.profile_mods_dir)
    # .mod belongs to modules — not override, not a .hak — so it is never offered.
    assert c.dev_move_target("Aielund", "modules", "camp.mod") is None


# -- UI: the right-click action (newtopic55's documented path) --------------- #


def test_context_menu_offers_move_to_development_for_an_override_file(
    qtbot, dev_controller
):
    win = MainWindow(dev_controller)
    qtbot.addWidget(win)
    md = dev_controller.pd.mod_item("Aielund")
    win._show_contents(md)
    assert win._contents.select_file(("override", "hotfix.utc"))

    menu = win._build_contents_menu()
    assert menu is not None
    assert "Move to Development" in [a.text() for a in menu.actions()]


def test_context_menu_omits_move_to_development_when_disabled(qtbot, tmp_path):
    controller = _make_controller(tmp_path, development_folder=False)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    md = controller.pd.mod_item("Aielund")
    win._show_contents(md)
    assert win._contents.select_file(("override", "hotfix.utc"))

    menu = win._build_contents_menu()
    assert menu is not None
    assert not any("Development" in a.text() for a in menu.actions())


def test_on_move_to_dev_moves_the_selected_file(qtbot, dev_controller):
    win = MainWindow(dev_controller)
    qtbot.addWidget(win)
    md = dev_controller.pd.mod_item("Aielund")
    win._show_contents(md)
    assert win._contents.select_file(("override", "hotfix.utc"))

    win._on_move_to_dev()

    payload = dev_controller.ctx.profile_mods_dir / "Aielund" / ".Mod Installer"
    assert (payload / "development" / "hotfix.utc").exists()


def test_on_move_to_dev_reports_when_nothing_selected(qtbot, dev_controller):
    win = MainWindow(dev_controller)
    qtbot.addWidget(win)
    win._contents_mod = "Aielund"

    win._on_move_to_dev()
    assert "Select a file in Contents first." in win.nit_status.mg_info.text()


def test_debug_menu_toggle_enables_the_development_folder_live(qtbot, tmp_path):
    """DbEnableDevelopmentFolder persists the choice and re-applies the mapper."""
    from vaultkeeper.config.settings import load_settings

    controller = _make_controller(tmp_path, development_folder=False)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert not controller.ctx.mapper.development_folder_enabled

    win._on_toggle("DbEnableDevelopmentFolder", True)
    assert controller.ctx.mapper.development_folder_enabled
    assert load_settings().enable_development_folder is True
    # Now live without reopening the profile.
    assert controller.dev_move_target("Aielund", "override", "hotfix.utc") == (
        "development",
        "Move to Development",
    )

    win._on_toggle("DbEnableDevelopmentFolder", False)
    assert not controller.ctx.mapper.development_folder_enabled
    assert load_settings().enable_development_folder is False


def test_settings_dialog_persists_enable_debug_menu(qtbot):
    """The Behaviour tab's Enable Debug Menu Options round-trips to settings."""
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    settings = Settings()
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert not dlg.debug_menu.isChecked()
    dlg.debug_menu.setChecked(True)
    dlg.apply_to(settings)
    assert settings.debug_options_menu is True
