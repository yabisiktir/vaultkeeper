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

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

#: Valid ``Settings.theme`` values (also the order shown in the Appearance tab).
THEMES = ("system", "light", "dark")


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
        pal.setColor(QPalette.ColorRole.ToolTipBase, text)
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


def apply_appearance(app: QApplication, *, font_point_size: int, theme: str) -> None:
    """Apply the persisted font size + theme to ``app`` (VB ``Restart()`` step).

    ``font_point_size <= 0`` leaves the platform default font untouched.
    ``theme == "system"`` leaves the platform default palette untouched.
    """
    if font_point_size > 0:
        f = app.font()
        f.setPointSize(font_point_size)
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
