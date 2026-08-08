"""Tests for wired Settings effects (window geometry, install-after-create)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.config.settings import Settings  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.main_window import MainWindow  # noqa: E402


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_window_geometry_saved_on_close(qtbot, tmp_path, monkeypatch):
    import vaultkeeper.config.settings as S

    captured = {"settings": Settings(remember_window_position=True)}
    monkeypatch.setattr(S, "load_settings", lambda *a, **k: captured["settings"])
    monkeypatch.setattr(
        S, "save_settings", lambda s, *a, **k: captured.__setitem__("settings", s)
    )
    win = MainWindow(_controller(tmp_path))
    qtbot.addWidget(win)
    win._save_geometry()
    assert captured["settings"].window_geometry != ""


def test_window_geometry_not_saved_when_off(qtbot, tmp_path, monkeypatch):
    import vaultkeeper.config.settings as S

    captured = {"settings": Settings(remember_window_position=False), "saved": False}
    monkeypatch.setattr(S, "load_settings", lambda *a, **k: captured["settings"])
    monkeypatch.setattr(
        S, "save_settings", lambda *a, **k: captured.__setitem__("saved", True)
    )
    win = MainWindow(_controller(tmp_path))
    qtbot.addWidget(win)
    win._save_geometry()
    assert captured["saved"] is False


def test_install_after_create_effect(qtbot, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    controller.create_mod("Solo")
    mod = tmp_path / "Profiles" / "P" / "Solo"
    (mod / "hak" / "x.hak").parent.mkdir(parents=True)
    (mod / "hak" / "x.hak").write_bytes(b"HAK")

    win = MainWindow(controller)
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "_install_after_create", lambda: True)
    monkeypatch.setattr(win, "selected_mod_names", lambda: ["Solo"])
    monkeypatch.setattr(win, "_run_installer_wizard", lambda name: (None, None))
    win._on_create_installer()
    assert controller.pd.mod_item("Solo").installed


def test_open_profile_honours_game_user_dir_override(tmp_path):
    from vaultkeeper.ui.controller import ProfileController

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    custom = tmp_path / "MyGameUser"
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=custom,
    )
    assert controller.ctx.game_user_dir == custom


# -- preferences that used to be stored and ignored ---------------------------- #
def _played(controller, mod: str):
    """Pretend a game of ``mod`` is in progress."""
    controller.play_loop.current_play_title = lambda: (mod, "Somewhere")


def test_select_game_mod_off_leaves_the_selection_alone(qtbot, tmp_path, monkeypatch):
    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    controller.create_mod("Played Mod")
    _played(controller, "Played Mod")
    settings = controller._settings()
    settings.select_game_mod = False
    monkeypatch.setattr(controller, "_settings", lambda: settings)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.refresh()
    picked = []
    monkeypatch.setattr(win, "_select_mod_by_name", lambda n: picked.append(n))
    win._apply_play_preferences()
    assert picked == []


def test_select_game_mod_on_selects_the_game_being_played(qtbot, tmp_path, monkeypatch):
    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    controller.create_mod("Played Mod")
    _played(controller, "Played Mod")
    settings = controller._settings()
    settings.select_game_mod = True
    monkeypatch.setattr(controller, "_settings", lambda: settings)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.refresh()
    picked = []
    monkeypatch.setattr(win, "_select_mod_by_name", lambda n: picked.append(n))
    win._apply_play_preferences()
    assert picked == ["Played Mod"]


def test_the_debug_mode_command_is_copied_when_asked_for(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    settings = controller._settings()
    settings.copy_debug_mode_on_play = "DebugMode 1"
    monkeypatch.setattr(controller, "_settings", lambda: settings)
    QApplication.clipboard().setText("")
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._apply_play_preferences()
    assert QApplication.clipboard().text() == "DebugMode 1"


def test_a_clipboard_already_holding_a_dm_command_is_left_alone(qtbot, tmp_path, monkeypatch):
    """VB refuses to overwrite one, so this does too."""
    from PySide6.QtWidgets import QApplication

    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    settings = controller._settings()
    settings.copy_debug_mode_on_play = "DebugMode 1"
    monkeypatch.setattr(controller, "_settings", lambda: settings)
    QApplication.clipboard().setText("dm_god")
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._apply_play_preferences()
    assert QApplication.clipboard().text() == "dm_god"


def test_the_mod_name_is_copied_only_when_starting_a_new_game(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    controller.create_mod("Fresh Mod")
    settings = controller._settings()
    settings.copy_mod_name_on_play = True
    settings.copy_debug_mode_on_play = ""
    monkeypatch.setattr(controller, "_settings", lambda: settings)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.refresh()
    monkeypatch.setattr(win, "selected_mod_names", lambda: ["Fresh Mod"])

    _played(controller, "")               # no game in progress
    QApplication.clipboard().setText("")
    win._apply_play_preferences()
    assert QApplication.clipboard().text() == "Fresh Mod"

    _played(controller, "Something Else")  # a game *is* in progress
    QApplication.clipboard().setText("")
    win._apply_play_preferences()
    assert QApplication.clipboard().text() == ""


def test_the_startup_config_check_can_be_switched_off(qtbot, tmp_path, monkeypatch):
    """It ran unconditionally, so unticking the box changed nothing."""
    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    settings = controller._settings()
    settings.validate_game_config_on_startup = False
    monkeypatch.setattr(controller, "_settings", lambda: settings)
    checked = []
    monkeypatch.setattr(
        controller, "startup_config_check", lambda: checked.append(1) or []
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._notify_config_drift()
    assert checked == []

    settings.validate_game_config_on_startup = True
    win._notify_config_drift()
    assert checked == [1]
