"""Vaultkeeper hands its resolved light/dark to an embedded Save Game Editor.

The editor detects ``editor_theme()`` on its host and opens matching it, so it
does not look out of place beside the app that launched it.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_editor_theme_follows_the_apps_light_dark(tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    # Resolved from the live palette (so "system" is handled), not the saved name.
    monkeypatch.setattr("vaultkeeper.ui.theme.is_dark", lambda *a, **k: True)
    assert controller.editor_theme() == "dark"
    monkeypatch.setattr("vaultkeeper.ui.theme.is_dark", lambda *a, **k: False)
    assert controller.editor_theme() == "light"


def test_set_class_level_editing_persists_for_the_embedded_editor(tmp_path):
    controller = _controller(tmp_path)
    assert controller._settings().enable_class_level_editing is False
    controller.set_class_level_editing(True)
    assert controller._settings().enable_class_level_editing is True
