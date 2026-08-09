"""Appearance helpers: global font size + light/dark/system theme.

BOUNDED PORT of the VB ``BasicFontAndColourEditor`` (see ``NIT.Menu.vb``
``RbnFontAndColour_Click`` / ``MsFontAndColour_Click``, which opens the Font page
and Colour page, writes ``My.Settings.Fonts`` and the colour settings, then calls
``Restart()`` to apply). The VB editor lets the user recolour and refont
individual UI elements one at a time; porting that whole per-element editor is
out of scope. This module ports only the high-value accessibility subset: one
application-wide font point size and one light/dark/system palette. This is a
deliberate simplification, not a 1:1 port of the VB form.

Kept import-safe and unit-testable without a running Qt event loop: building a
``QPalette`` does not require ``QApplication`` to be constructed first, only for
``apply_appearance`` (which touches ``QApplication.instance()``-level state).
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

#: Valid ``Settings.theme`` values (also the order shown in the Appearance tab).
THEMES = ("system", "light", "dark")

#: Status colours, per background. A single colour cannot serve both: the greens
#: and ambers originally used were picked against white and dropped to 3.2–3.9:1
#: on the dark theme's #1e1e1e, under the 4.5:1 needed to read comfortably — and
#: these mark whether a mod is *installed*, which is the main list's whole point.
#: Every value below clears 4.5:1 against the background it is chosen for.
_STATUS_COLOURS: dict[str, tuple[str, str]] = {
    # name          on light     on dark
    "installed": ("#2E7D32", "#66BB6A"),
    "overridden": ("#8F5600", "#FFA726"),  # the light amber was 4.24:1 — also raised
    "duplicate": ("#C80000", "#EF5350"),
    "disabled": ("#6E6E6E", "#9E9E9E"),
}


#: The font the application started with, captured before anything is applied.
_BASE_FONT: QFont | None = None


def _base_font(app: QApplication) -> QFont:
    global _BASE_FONT
    if _BASE_FONT is None:
        _BASE_FONT = QFont(app.font())
    return _BASE_FONT


def is_dark(palette: QPalette | None = None) -> bool:
    """Whether the active palette is a dark one.

    Read from the palette rather than the saved theme name so that "system"
    is classified by what the OS actually gave us.
    """
    if palette is None:
        app = QApplication.instance()
        if app is None:
            return False
        palette = app.palette()
    window = palette.color(QPalette.ColorRole.Window)
    return window.lightness() < 128


#: What each status colour marks, for the Appearance page. The label is the
#: user's name for it; the description says where it shows, because "Overridden"
#: means nothing on its own.
STATUS_COLOUR_LABELS: dict[str, tuple[str, str]] = {
    "installed": ("Installed", "A mod whose files are all in the game"),
    "overridden": ("Overridden", "A mod some of whose files another mod has replaced"),
    "duplicate": ("Conflict", "A duplicated name, or a file that clashes"),
    "disabled": ("Unavailable", "Rows that are present but not usable"),
}


def default_status_colour(name: str, *, dark: bool = False) -> str:
    """The built-in colour for a status, as a hex string."""
    light_value, dark_value = _STATUS_COLOURS.get(name, ("#000000", "#FFFFFF"))
    return dark_value if dark else light_value


def status_colour(name: str, palette: QPalette | None = None) -> QColor:
    """A status colour that stays legible on the current background.

    A saved override wins outright, on either background: it is the user's
    choice, and second-guessing it here would make the picker a suggestion box.
    """
    override = _status_overrides().get(name)
    if override:
        colour = QColor(override)
        if colour.isValid():
            return colour
    return QColor(default_status_colour(name, dark=is_dark(palette)))


def _status_overrides() -> dict[str, str]:
    from vaultkeeper.config.settings import load_settings

    try:
        return load_settings().status_colours or {}
    except Exception:  # settings must never be able to break painting
        return {}


def build_palette(theme: str) -> QPalette | None:
    """Build a ``QPalette`` for ``theme``, or ``None`` to mean "leave the default".

    ``"system"`` returns ``None`` — the caller should simply not touch the
    application palette, leaving whatever the OS/Qt style already provides.
    ``"light"`` and ``"dark"`` return small, self-contained palettes; this is not
    an attempt to reproduce the VB editor's per-element colour scheme, just a
    sensible bounded light/dark pair.
    """
    if theme == "dark":
        pal = QPalette()
        window = QColor(43, 43, 43)  # #2b2b2b
        base = QColor(30, 30, 30)
        text = QColor(255, 255, 255)
        highlight = QColor(61, 130, 214)
        pal.setColor(QPalette.ColorRole.Window, window)
        pal.setColor(QPalette.ColorRole.WindowText, text)
        pal.setColor(QPalette.ColorRole.Base, base)
        pal.setColor(QPalette.ColorRole.AlternateBase, window)
        # ToolTipBase is the *background*. Setting it to the text colour painted a
        # white box with white text in it — every tooltip in the dark theme was a
        # blank rectangle. Slightly lighter than the window so the tip reads as
        # sitting above it.
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(60, 60, 60))
        pal.setColor(QPalette.ColorRole.ToolTipText, text)
        pal.setColor(QPalette.ColorRole.Text, text)
        pal.setColor(QPalette.ColorRole.Button, window)
        pal.setColor(QPalette.ColorRole.ButtonText, text)
        pal.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        pal.setColor(QPalette.ColorRole.Link, highlight)
        pal.setColor(QPalette.ColorRole.Highlight, highlight)
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        return pal
    if theme == "light":
        pal = QPalette()
        window = QColor(240, 240, 240)
        base = QColor(255, 255, 255)
        text = QColor(0, 0, 0)
        highlight = QColor(0, 120, 215)
        pal.setColor(QPalette.ColorRole.Window, window)
        pal.setColor(QPalette.ColorRole.WindowText, text)
        pal.setColor(QPalette.ColorRole.Base, base)
        pal.setColor(QPalette.ColorRole.AlternateBase, window)
        pal.setColor(QPalette.ColorRole.ToolTipBase, window)
        pal.setColor(QPalette.ColorRole.ToolTipText, text)
        pal.setColor(QPalette.ColorRole.Text, text)
        pal.setColor(QPalette.ColorRole.Button, window)
        pal.setColor(QPalette.ColorRole.ButtonText, text)
        pal.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        pal.setColor(QPalette.ColorRole.Link, highlight)
        pal.setColor(QPalette.ColorRole.Highlight, highlight)
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        return pal
    return None  # "system" (or anything unrecognised) — leave the app default.


def apply_appearance(
    app: QApplication,
    *,
    font_point_size: int,
    theme: str,
    font_family: str = "",
) -> None:
    """Apply the persisted font + theme to ``app`` (VB ``Restart()`` step).

    ``font_point_size <= 0`` and an empty ``font_family`` each leave that half of
    the platform default font untouched. ``theme == "system"`` leaves the
    platform default palette untouched.
    """
    # Always start from the font the application launched with, never from the
    # one currently applied. Otherwise nothing can be *un*set: picking "System
    # default" after a custom font would leave the custom font in place, since
    # "leave it alone" and "put it back" look identical from the current font.
    base = _base_font(app)
    f = QFont(base)
    if font_point_size > 0:
        f.setPointSize(font_point_size)
    if font_family:
        f.setFamily(font_family)
    if f != app.font():
        app.setFont(f)
    if theme != "system":
        # Switch to Fusion first. The native styles paint their chrome from the
        # OS appearance and ignore most of an application palette: on macOS that
        # left the toolbar and the ribbon's tab strip dark while every panel
        # below them went light, which is not a theme so much as two halves of
        # different ones. Fusion honours the palette throughout, and does so
        # identically on Windows, macOS and Linux — which this ships on.
        app.setStyle("Fusion")
        pal = build_palette(theme)
        if pal:
            app.setPalette(pal)
