"""Tests for the appearance helpers (BOUNDED PORT of the VB font/colour editor).

See ``vaultkeeper.ui.theme`` for what "bounded" means here: a global font point
size + a light/dark/system theme, not the full per-element VB
``BasicFontAndColourEditor``.
"""

from __future__ import annotations

import pytest
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


# -- the widget style, which decides whether the palette is honoured ----------#
def test_choosing_a_theme_switches_to_fusion():
    """The native styles paint chrome from the OS and ignore the palette.

    On macOS that left the toolbar and the ribbon's tab strip dark while every
    panel below them went light — two halves of different themes in one window.
    Fusion honours the palette throughout, and identically on all three
    platforms this ships on.
    """
    app = _app()
    original = app.style().objectName()
    try:
        apply_appearance(app, font_point_size=0, theme="light")
        assert app.style().objectName().lower() == "fusion"
    finally:
        app.setStyle(original)


def test_the_system_theme_keeps_the_platform_style():
    """"System" means the OS decides — including how widgets are drawn."""
    app = _app()
    original = app.style().objectName()
    try:
        apply_appearance(app, font_point_size=0, theme="system")
        assert app.style().objectName() == original
    finally:
        app.setStyle(original)


# -- status colours must stay legible on the background they land on ----------#
def _relative_luminance(colour):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = colour.red(), colour.green(), colour.blue()
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a, b):
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("name", ["installed", "overridden", "duplicate", "disabled"])
def test_status_colours_are_readable_on_their_own_theme(theme, name):
    """These mark whether a mod is installed — the main list's whole point.

    The greens and ambers this replaced were picked against white and fell to
    3.2-3.9:1 on the dark theme's panels, under the 4.5:1 text needs; the amber
    was only 4.24:1 even on white.
    """
    from vaultkeeper.ui.theme import status_colour

    palette = build_palette(theme)
    background = palette.color(QPalette.ColorRole.Base)
    assert _contrast(status_colour(name, palette), background) >= 4.5


def test_a_dark_palette_is_recognised_as_dark():
    from vaultkeeper.ui.theme import is_dark

    assert is_dark(build_palette("dark"))
    assert not is_dark(build_palette("light"))


def test_the_same_status_reads_differently_per_theme():
    """One colour cannot serve both backgrounds; that was the bug."""
    from vaultkeeper.ui.theme import status_colour

    for name in ("installed", "overridden", "duplicate"):
        assert status_colour(name, build_palette("light")) != status_colour(
            name, build_palette("dark")
        )


# -- every palette must be legible ---------------------------------------------- #
def _luminance(colour) -> float:
    """Perceived brightness, 0..1 (WCAG relative luminance, sRGB linearised)."""

    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    r, g, b = colour.red(), colour.green(), colour.blue()
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(fore, back) -> float:
    a, b = sorted((_luminance(fore), _luminance(back)), reverse=True)
    return (a + 0.05) / (b + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    "text_role,base_role,minimum",
    [
        # WCAG AA for body text is 4.5:1.
        ("ToolTipText", "ToolTipBase", 4.5),
        ("WindowText", "Window", 4.5),
        ("Text", "Base", 4.5),
        ("ButtonText", "Button", 4.5),
        # Selected text sits on the platform's own selection colour: white on
        # Windows' #0078d7 measures 4.499:1, and refusing the system blue over a
        # thousandth would be the test dictating to the platform. WCAG's 3:1 bar
        # for UI components is the right one here, and still catches the failure
        # this exists for — white on white is 1:1.
        ("HighlightedText", "Highlight", 3.0),
    ],
)
def test_every_foreground_is_readable_on_its_background(
    theme, text_role, base_role, minimum
):
    """The dark theme once set ToolTipBase to the *text* colour.

    White on white: every tooltip was a blank white rectangle, which reads as a
    rendering glitch rather than a missing tooltip. Nothing in the suite noticed,
    because a palette is only wrong when someone looks at it — so this looks.
    """
    from PySide6.QtGui import QPalette

    palette = build_palette(theme)
    assert palette is not None
    fore = palette.color(getattr(QPalette.ColorRole, text_role))
    back = palette.color(getattr(QPalette.ColorRole, base_role))
    ratio = _contrast(fore, back)
    assert ratio >= minimum, (
        f"{theme}: {text_role} on {base_role} is {ratio:.2f}:1 "
        f"({fore.name()} on {back.name()}) — below the {minimum}:1 threshold"
    )
