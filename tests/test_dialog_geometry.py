"""Dialog sizing and geometry memory.

Owner-reported: "the default size of opened items do not start with a good
size, where some tabs are not by default completely visible/truncated. The app
also does not remember the previous state (or give the option to reset)."
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog, QLabel, QTabWidget, QVBoxLayout, QWidget

from vaultkeeper.config.settings import load_settings, save_settings
from vaultkeeper.ui import geometry


class _Tabbed(QDialog):
    """A dialog whose tab labels are wider than its pages — the shape that broke."""

    def __init__(self, tabs: int = 5, label: str = "Tab") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        for i in range(tabs):
            page = QWidget()
            inner = QVBoxLayout(page)
            inner.addWidget(QLabel("x"))
            self.tabs.addTab(page, f"{label} {i}")
        layout.addWidget(self.tabs)
        geometry.remember(self, "TestTabbed", 200, 120)


def _shown(qtbot, dialog):
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog


def _assert_tabs_fit(dialog, tabs) -> None:
    """The tab bar fits — unless the screen is too small for it to.

    The two are one invariant, not two: `geometry` grows a dialog to fit its tab
    bar *and* caps it to the screen, and the cap wins. A minimum wider than the
    display cannot be satisfied or escaped, so Qt scrolls the bar instead, which
    is the deliberate fallback.

    This matters off macOS: the offscreen platform reports an 800x800 screen
    everywhere, and Windows' default font makes the same seven labels 1056px
    wide against roughly 700 on macOS. Asserting only "it fits" passes on the
    machine it was written on and fails on the one that runs CI.
    """
    from PySide6.QtWidgets import QApplication

    needed = tabs.tabBar().sizeHint().width()
    if tabs.width() >= needed:
        return
    available = (dialog.screen() or QApplication.primaryScreen()).availableGeometry()
    assert dialog.width() >= int(available.width() * 0.9) - 1, (
        f"the tab bar needs {needed}px, the dialog is {dialog.width()}px and the "
        f"screen is {available.width()}px — it should have grown"
    )


def test_a_dialog_opens_wide_enough_for_every_tab(qtbot):
    """A hidden tab is hidden functionality — the Settings dialog was cutting
    off its seventh tab before anyone touched it."""
    dlg = _shown(qtbot, _Tabbed(tabs=6, label="Tab Label"))
    _assert_tabs_fit(dlg, dlg.tabs)


def test_the_hard_coded_size_is_a_floor_not_the_answer(qtbot):
    """200x120 was asked for; the content needs more, so the content wins."""
    dlg = _shown(qtbot, _Tabbed())
    assert dlg.width() > 200


def test_a_dialog_never_opens_bigger_than_the_screen(qtbot):
    """And the tab-bar minimum must respect that too: a minimum wider than the
    display cannot be satisfied *or* escaped — Qt scrolling the bar is better."""
    from PySide6.QtWidgets import QApplication

    dlg = _shown(qtbot, _Tabbed(tabs=40, label="A Rather Long Tab Label"))
    available = (dlg.screen() or QApplication.primaryScreen()).availableGeometry()
    assert dlg.width() <= available.width()
    assert dlg.height() <= available.height()


# -- Remembering ---------------------------------------------------------------- #
@pytest.fixture()
def remembering():
    settings = load_settings()
    settings.remember_window_position = True
    settings.dialog_geometry = {}
    save_settings(settings)
    return settings


def test_a_resized_dialog_comes_back_the_same_size(qtbot, remembering):
    first = _shown(qtbot, _Tabbed())
    first.resize(first.width() + 90, first.height() + 40)
    wanted = (first.width(), first.height())
    first.accept()  # finished() is the one signal every exit route emits

    second = _shown(qtbot, _Tabbed())
    assert (second.width(), second.height()) == wanted


def test_nothing_is_remembered_when_the_preference_is_off(qtbot, remembering):
    remembering.remember_window_position = False
    save_settings(remembering)

    dlg = _shown(qtbot, _Tabbed())
    dlg.resize(dlg.width() + 120, dlg.height())
    dlg.accept()

    assert load_settings().dialog_geometry == {}


def test_reset_window_layout_forgets_dialog_sizes(qtbot, remembering):
    """A remembered size can itself be the problem — a window dragged onto a
    monitor that is not there any more. There has to be a way back."""
    dlg = _shown(qtbot, _Tabbed())
    dlg.resize(dlg.width() + 50, dlg.height())
    dlg.accept()
    assert load_settings().dialog_geometry, "something was remembered"

    geometry.clear_all()
    assert load_settings().dialog_geometry == {}


def test_each_dialog_is_remembered_separately(qtbot, remembering):
    first = _shown(qtbot, _Tabbed())
    first.resize(first.width() + 70, first.height())
    first.accept()

    other = QDialog()
    QVBoxLayout(other).addWidget(QLabel("small"))
    geometry.remember(other, "SomethingElse", 300, 200)
    _shown(qtbot, other)

    assert set(load_settings().dialog_geometry) == {"TestTabbed"}


def test_the_settings_dialog_shows_all_seven_tabs(qtbot):
    """The screen that was actually reported."""
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    dlg = _shown(qtbot, SettingsDialog(load_settings(), None))
    tabs = dlg.findChild(QTabWidget)
    assert tabs.count() == 7
    _assert_tabs_fit(dlg, tabs)
