"""First-run auto-setup: establish a default profile from the discovered install.

Faithful to VB Paths.vb (~1615-1643) — the tool never drops the user into an empty
profile-less state; it auto-creates a default profile named for the edition.
"""

from __future__ import annotations

from pathlib import Path

from nwnfile.editions import Edition
from nwnfile.locations import GameInstall

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.ui.session import (
    DEFAULT_EE_PROFILE,
    DEFAULT_PROFILE,
    auto_configure_first_run,
)


def _settings_file(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    save_settings(Settings(store_root=str(tmp_path / "store")), path)
    return path


def _install(tmp_path: Path, edition: Edition) -> list[GameInstall]:
    root = tmp_path / "NWN"
    root.mkdir(exist_ok=True)
    return [GameInstall(root=root, edition=edition)]


def _no_real_game_scan(monkeypatch):
    # Don't auto-detect + scan the developer's real ~/Documents/Neverwinter Nights.
    monkeypatch.setattr("vaultkeeper.ui.session.default_game_user_path", lambda **_: None)


def test_auto_configure_creates_ee_default(tmp_path, monkeypatch):
    _no_real_game_scan(monkeypatch)
    settings_path = _settings_file(tmp_path)
    ctrl = auto_configure_first_run(
        settings_path=settings_path,
        discover=lambda: _install(tmp_path, Edition.ENHANCED),
    )
    assert ctrl is not None
    settings = load_settings(settings_path)
    assert settings.active_profile == DEFAULT_EE_PROFILE
    assert settings.nwn_path == str(tmp_path / "NWN")
    assert (tmp_path / "store" / "Profiles" / DEFAULT_EE_PROFILE).is_dir()


def test_auto_configure_creates_classic_default(tmp_path, monkeypatch):
    _no_real_game_scan(monkeypatch)
    settings_path = _settings_file(tmp_path)
    ctrl = auto_configure_first_run(
        settings_path=settings_path,
        discover=lambda: _install(tmp_path, Edition.DIAMOND),
    )
    assert ctrl is not None
    assert load_settings(settings_path).active_profile == DEFAULT_PROFILE


def test_auto_configure_no_install_returns_none(tmp_path):
    settings_path = _settings_file(tmp_path)
    ctrl = auto_configure_first_run(settings_path=settings_path, discover=lambda: [])
    assert ctrl is None
    # No profile was invented.
    assert load_settings(settings_path).active_profile is None


def test_auto_configure_is_noop_when_profile_active(tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(
        Settings(store_root=str(tmp_path / "store"), active_profile="My Mods"),
        settings_path,
    )
    called = []
    ctrl = auto_configure_first_run(
        settings_path=settings_path,
        discover=lambda: called.append(1) or _install(tmp_path, Edition.ENHANCED),
    )
    assert ctrl is None
    assert not called  # discovery is skipped entirely when a profile exists
    assert load_settings(settings_path).active_profile == "My Mods"


# -- MainWindow first-run import offer ------------------------------------- #
def test_offer_legacy_import_prompts_when_store_and_empty(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)

    monkeypatch.setattr(
        "vaultkeeper.ui.session.detect_legacy_store", lambda: tmp_path / "NIT Store"
    )
    seen = {}
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: seen.setdefault("asked", True)
        or QMessageBox.StandardButton.No,
    )
    win.offer_legacy_import()
    assert seen.get("asked")  # prompted (empty profile + store present)


def test_offer_legacy_import_silent_without_store(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)

    monkeypatch.setattr("vaultkeeper.ui.session.detect_legacy_store", lambda: None)
    called = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: called.append(1)
    )
    win.offer_legacy_import()
    assert not called  # no store -> no prompt
