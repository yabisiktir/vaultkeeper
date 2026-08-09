"""Remembering how big a dialog was, and opening it big enough in the first place.

Two separate problems, both reported together:

**Nothing fitted.** Dialogs called ``resize(560, 380)`` with a number chosen when
they had fewer tabs and shorter labels, and a hard-coded size does not grow with
the content. The Settings dialog's tab bar needed 709px and had 695, so a tab was
cut off before anyone touched anything. :func:`fit_to_content` makes the opening
size at least what the layout asks for, so a screen never *starts* truncated.

**Nothing was remembered.** Resizing a dialog and reopening it put it back the
way it was. Geometry now persists per screen, under the same
``remember_window_position`` preference the main window uses, and *Reset Window
Layout* clears it — a remembered size can itself become the problem (a window
dragged onto a monitor that is no longer there), so there has to be a way back.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QObject
from PySide6.QtWidgets import QApplication, QWidget

#: Never open a dialog larger than this share of the screen it is on. A layout
#: can ask for more room than a laptop has, and a window taller than the display
#: puts its buttons where nobody can reach them.
_MAX_SCREEN_FRACTION = 0.9


def fit_to_content(dialog: QWidget, width: int = 0, height: int = 0) -> None:
    """Size ``dialog`` to at least its layout's request, and at most the screen.

    ``width``/``height`` are the preferred size — what the old ``resize`` call
    said. They are treated as a floor to grow from, not as the answer.
    """
    dialog.ensurePolished()
    _require_room_for_tabs(dialog)
    layout = dialog.layout()
    if layout is not None:
        layout.activate()

    hint = dialog.sizeHint()
    want_w = max(width, hint.width(), dialog.minimumSizeHint().width())
    want_h = max(height, hint.height(), dialog.minimumSizeHint().height())
    dialog.resize(*_capped(dialog, want_w, want_h))

    # A second pass, because the shortfall is only measurable once the layout has
    # run at the new width — and the first pass is what makes that width real.
    if layout is not None:
        layout.activate()
    short = _tab_bar_shortfall(dialog)
    if short > 0:
        dialog.resize(*_capped(dialog, dialog.width() + short, dialog.height()))


def _capped(dialog: QWidget, width: int, height: int) -> tuple[int, int]:
    """Keep a size inside the screen: a window taller than the display puts its
    buttons where nobody can reach them."""
    screen = dialog.screen() or QApplication.primaryScreen()
    if screen is None:
        return width, height
    available = screen.availableGeometry()
    return (
        min(width, int(available.width() * _MAX_SCREEN_FRACTION)),
        min(height, int(available.height() * _MAX_SCREEN_FRACTION)),
    )


def _require_room_for_tabs(dialog: QWidget) -> None:
    """Make every tab bar's full width a hard minimum for its tab widget.

    Stating it as a minimum lets the layout carry it up to the dialog, which is
    more reliable than adding pixels by hand — the arithmetic has to guess at
    margins the layout already knows.
    """
    from PySide6.QtWidgets import QTabWidget

    # Capped by the screen. A minimum wider than the display is worse than a
    # clipped tab: the window cannot be made to fit at all, and Qt will not let
    # the user shrink it. Qt scrolls the bar in that case, which is the right
    # fallback.
    ceiling, _ = _capped(dialog, 1 << 24, 0)
    for tabs in dialog.findChildren(QTabWidget):
        needed = min(tabs.tabBar().sizeHint().width(), ceiling)
        if needed > tabs.minimumWidth():
            tabs.setMinimumWidth(needed)


def _tab_bar_shortfall(dialog: QWidget) -> int:
    """How many pixels short of showing every tab label the dialog is.

    A ``QTabWidget``'s own size hint is driven by its *pages*, so a dialog can
    satisfy it and still cut the tab bar off — which is exactly what Settings
    did: seven tabs wanting 709px in a bar given 695. A hidden tab is hidden
    functionality, so this is a floor, not a nicety.
    """
    from PySide6.QtWidgets import QTabWidget

    worst = 0
    for tabs in dialog.findChildren(QTabWidget):
        if not tabs.isVisible() and tabs.width() == 0:
            continue
        worst = max(worst, tabs.tabBar().sizeHint().width() - tabs.width())
    return worst


def restore(dialog: QWidget, key: str) -> bool:
    """Restore a remembered size/position for ``key``. True if one was applied."""
    from vaultkeeper.config.settings import load_settings

    settings = load_settings()
    if not settings.remember_window_position:
        return False
    saved = (settings.dialog_geometry or {}).get(key)
    if not saved:
        return False
    try:
        dialog.restoreGeometry(QByteArray.fromBase64(saved.encode("ascii")))
    except (ValueError, TypeError):
        return False
    return True


def save(dialog: QWidget, key: str) -> None:
    """Remember ``dialog``'s current geometry under ``key``."""
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    if not settings.remember_window_position:
        return
    geometry = bytes(dialog.saveGeometry().toBase64()).decode("ascii")
    stored = dict(settings.dialog_geometry or {})
    if stored.get(key) == geometry:
        return
    stored[key] = geometry
    settings.dialog_geometry = stored
    save_settings(settings)


def clear_all() -> None:
    """Forget every remembered dialog size (Reset Window Layout)."""
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    if not settings.dialog_geometry:
        return
    settings.dialog_geometry = {}
    save_settings(settings)


def remember(dialog: QWidget, key: str, width: int = 0, height: int = 0) -> None:
    """Give a dialog a sensible opening size and a memory. Call once, in ``__init__``.

    The sizing happens on **first show**, not here: ``__init__`` calls this
    before it has built the widgets it is going to measure, and a ``sizeHint``
    taken from an empty dialog is how the hard-coded sizes came to be wrong in
    the first place.

    Content first, then anything remembered on top — a saved size is what the
    user chose and outranks our arithmetic, but with none saved the dialog must
    still open showing all of itself.
    """
    dialog.resize(width or dialog.width(), height or dialog.height())
    # An event filter, not a patched showEvent. Assigning a closure over the
    # dialog to ``dialog.showEvent`` makes a reference cycle through the
    # widget's __dict__, and that changed destruction order enough to delete a
    # parented dialog out from under its owner (the help viewer, at teardown).
    # A filter parented to the dialog dies with it and owns nothing.
    dialog.installEventFilter(_Sizer(dialog, key, width, height))

    # finished() covers every way out of a QDialog — accept, reject, Esc, the
    # close button — and is the only one that does.
    finished = getattr(dialog, "finished", None)
    if finished is not None:
        finished.connect(lambda _result=0: save(dialog, key))


class _Sizer(QObject):
    """Sizes a dialog the first time it is shown, and saves it when it closes."""

    def __init__(self, dialog: QWidget, key: str, width: int, height: int) -> None:
        super().__init__(dialog)
        self._key = key
        self._width = width
        self._height = height
        self._sized = False

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 (Qt override)
        kind = event.type()
        if kind == QEvent.Type.Show and not self._sized:
            self._sized = True
            fit_to_content(watched, self._width, self._height)
            restore(watched, self._key)
        elif kind == QEvent.Type.Close:
            # For a plain QWidget there is no finished() to lean on.
            save(watched, self._key)
        return False
