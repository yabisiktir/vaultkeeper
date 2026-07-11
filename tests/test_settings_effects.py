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
