"""Tests for profile listing and switching."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings
from vaultkeeper.ui.session import list_profiles, switch_profile


def _settings(tmp_path: Path, **kw) -> Settings:
    return Settings(store_root=str(tmp_path / "Store"), **kw)


def test_list_profiles_empty(tmp_path):
    assert list_profiles(_settings(tmp_path)) == []


def test_list_profiles_returns_sorted_names(tmp_path):
    settings = _settings(tmp_path)
    profiles = settings.resolved_store().profiles
    for name in ("Zeta", "Alpha", "Mango"):
        (profiles / name).mkdir(parents=True)
    (profiles / "not_a_dir.txt").write_text("x")
    assert list_profiles(settings) == ["Alpha", "Mango", "Zeta"]


def test_switch_profile_persists_and_opens(tmp_path):
    game_root = tmp_path / "NWN"
    game_root.mkdir()
    settings_path = tmp_path / "settings.json"
    settings = _settings(tmp_path, nwn_path=str(game_root))

    controller = switch_profile(
        "My Mods", settings=settings, settings_path=settings_path
    )
    assert controller is not None
    # The profile's mods directory was created and the choice persisted.
    assert (settings.resolved_store().profile_dir("My Mods")).is_dir()
    assert settings.active_profile == "My Mods"

    # A reload from the settings file sees the active profile.
    from vaultkeeper.config.settings import load_settings

    assert load_settings(settings_path).active_profile == "My Mods"
