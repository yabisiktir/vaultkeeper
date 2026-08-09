"""Fonts and colours (VB customisefonts.htm / customisecolours.htm).

VB keeps a font per UI element (11) and a colour per element (25). This port
paints with four semantic colours and one font, and offers exactly those: a
picker for a colour nothing reads would be a preference that lies to the person
setting it — the same defect shape as a setting nothing reads.
"""

from __future__ import annotations

import pytest

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.ui import theme
from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog


@pytest.fixture()
def settings() -> Settings:
    s = load_settings()
    s.status_colours = {}
    s.font_family = ""
    save_settings(s)
    return s


def _appearance(qtbot, settings: Settings) -> SettingsDialog:
    dlg = SettingsDialog(settings, None)
    qtbot.addWidget(dlg)
    return dlg


def test_every_colour_the_app_paints_with_is_offered(qtbot, settings):
    """And only those. The list of pickers and the list of colours the code
    actually asks for must be the same list."""
    dlg = _appearance(qtbot, settings)
    assert set(dlg._colour_buttons) == set(theme.STATUS_COLOUR_LABELS)
    assert set(dlg._colour_buttons) == set(theme._STATUS_COLOURS)


def test_an_unset_colour_follows_the_theme(qtbot, settings):
    dlg = _appearance(qtbot, settings)
    button = dlg._colour_buttons["installed"]
    assert button.value() == ""
    assert "Theme default" in button.text()
    assert theme.status_colour("installed").name().lower() == (
        theme.default_status_colour("installed").lower()
    )


def test_a_chosen_colour_is_used_as_given(qtbot, settings):
    """Not adjusted for contrast: it is the user's choice, and second-guessing
    it would make the picker a suggestion box."""
    dlg = _appearance(qtbot, settings)
    dlg._colour_buttons["installed"]._value = "#ff00ff"
    dlg.apply_to(settings)
    save_settings(settings)

    assert theme.status_colour("installed").name() == "#ff00ff"


def test_clearing_a_colour_gives_it_back_to_the_theme(qtbot, settings):
    """"Unset" has to stay reachable — saving today's default as a value would
    freeze it, and the theme could never take the colour back."""
    settings.status_colours = {"installed": "#ff00ff"}
    save_settings(settings)

    dlg = _appearance(qtbot, settings)
    dlg._colour_buttons["installed"]._value = ""
    dlg.apply_to(settings)
    save_settings(settings)

    assert load_settings().status_colours == {}
    assert theme.status_colour("installed").name().lower() == (
        theme.default_status_colour("installed").lower()
    )


def test_the_default_colours_still_differ_per_background(qtbot, settings):
    """The light/dark pair is why an override is stored once and applied to
    both: only the defaults know which background they were picked for."""
    assert theme.default_status_colour("installed", dark=False) != (
        theme.default_status_colour("installed", dark=True)
    )


def test_a_font_family_can_be_chosen_and_cleared(qtbot, settings):
    dlg = _appearance(qtbot, settings)
    assert dlg.font_family.currentIndex() == 0
    assert dlg.font_family.itemText(0) == "System default"

    dlg.font_family.setCurrentIndex(2)
    chosen = dlg.font_family.currentText()
    dlg.apply_to(settings)
    assert settings.font_family == chosen

    dlg.font_family.setCurrentIndex(0)
    dlg.apply_to(settings)
    assert settings.font_family == "", "the platform default is not a family name"


def test_the_font_is_applied_without_disturbing_the_size(qtbot, settings):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    before = app.font().pointSize()
    try:
        theme.apply_appearance(
            app, font_point_size=0, theme="system", font_family="Courier"
        )
        assert app.font().family() == "Courier"
        assert app.font().pointSize() == before, "size was not asked about"
    finally:
        theme.apply_appearance(app, font_point_size=0, theme="system", font_family="")


def test_choosing_the_system_default_puts_the_font_back(qtbot, settings):
    """"Leave it alone" and "put it back" look identical from the current font,
    so applying always starts from the font the app launched with. Without that,
    a custom font could be changed but never undone until a restart — and the
    setting would look broken.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    original = app.font().family()
    try:
        theme.apply_appearance(
            app, font_point_size=0, theme="system", font_family="Courier"
        )
        assert app.font().family() == "Courier"

        theme.apply_appearance(app, font_point_size=0, theme="system", font_family="")
        assert app.font().family() == original
    finally:
        theme.apply_appearance(app, font_point_size=0, theme="system", font_family="")


def test_broken_settings_never_break_painting(qtbot, settings, monkeypatch):
    """status_colour runs on every row of the mod list; it must not be the thing
    that takes the window down if the settings file is unreadable."""
    monkeypatch.setattr(
        "vaultkeeper.config.settings.load_settings",
        lambda *a, **k: (_ for _ in ()).throw(OSError("no settings")),
    )
    assert theme.status_colour("installed").isValid()
