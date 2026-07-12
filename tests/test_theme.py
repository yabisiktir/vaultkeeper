"""Tests for the appearance helpers (BOUNDED PORT of the VB font/colour editor).

See ``vaultkeeper.ui.theme`` for what "bounded" means here: a global font point
size + a light/dark/system theme, not the full per-element VB
``BasicFontAndColourEditor``.
"""

from __future__ import annotations

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.ui.theme import THEMES, apply_appearance, build_palette


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


# -- build_palette ----------------------------------------------------------- #


def test_build_palette_system_is_none():
    assert build_palette("system") is None


def test_build_palette_unknown_is_none():
    assert build_palette("not-a-theme") is None


def test_build_palette_light_and_dark_return_palettes():
    light = build_palette("light")
    dark = build_palette("dark")
    assert isinstance(light, QPalette)
    assert isinstance(dark, QPalette)


def test_build_palette_light_and_dark_windows_differ():
    light = build_palette("light")
    dark = build_palette("dark")
    assert light.color(QPalette.ColorRole.Window) != dark.color(QPalette.ColorRole.Window)


def test_themes_tuple_contents():
    assert THEMES == ("system", "light", "dark")


# -- apply_appearance ---------------------------------------------------------#


def test_apply_appearance_sets_font_point_size_when_positive():
    app = _app()
    original = app.font()
    try:
        apply_appearance(app, font_point_size=18, theme="system")
        assert app.font().pointSize() == 18
    finally:
        app.setFont(original)


def test_apply_appearance_leaves_font_when_zero():
    app = _app()
    original = app.font()
    original_size = original.pointSize()
    try:
        apply_appearance(app, font_point_size=0, theme="system")
        assert app.font().pointSize() == original_size
    finally:
        app.setFont(original)


def test_apply_appearance_leaves_palette_for_system_theme():
    app = _app()
    original = app.palette()
    try:
        apply_appearance(app, font_point_size=0, theme="system")
        assert app.palette() == original
    finally:
        app.setPalette(original)


def test_apply_appearance_sets_dark_palette():
    app = _app()
    original = app.palette()
    try:
        apply_appearance(app, font_point_size=0, theme="dark")
        assert app.palette().color(QPalette.ColorRole.Window) == build_palette(
            "dark"
        ).color(QPalette.ColorRole.Window)
    finally:
        app.setPalette(original)


# -- Settings round-trip ------------------------------------------------------#


def test_settings_defaults_for_appearance():
    s = Settings()
    assert s.font_point_size == 0
    assert s.theme == "system"


def test_settings_round_trips_font_and_theme(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(font_point_size=14, theme="dark")
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.font_point_size == 14
    assert loaded.theme == "dark"
