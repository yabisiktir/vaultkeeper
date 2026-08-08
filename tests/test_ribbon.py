"""Tests for the Ribbon widget."""

from __future__ import annotations

import pytest

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.ribbon import ADDED_BUTTONS, RIBBON_TABS, VB_RIBBON_TABS, Ribbon


def test_seven_tabs_in_order(qtbot):
    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    titles = [ribbon.tabText(i) for i in range(ribbon.count())]
    assert titles == [
        "Play",
        "Work with Mods",
        "Work with Installers",
        "Tools",
        "Diagnose",
        "Backup and Recovery",
        "Customise",
    ]


def test_all_buttons_present(qtbot):
    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    expected = {item.action for _, items in RIBBON_TABS for item in items}
    assert set(ribbon.buttons) == expected


def test_every_button_has_a_real_icon(qtbot):
    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    missing = [
        item.action
        for _, items in RIBBON_TABS
        for item in items
        if not R.icon_exists(item.image)
    ]
    assert not missing, f"ribbon buttons with no asset: {missing}"


def test_click_emits_action_id(qtbot):
    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    with qtbot.waitSignal(ribbon.action_triggered) as sig:
        ribbon.button("RbnPlay").click()
    assert sig.args == ["RbnPlay"]


def test_two_line_captions(qtbot):
    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    assert ribbon.button("RbnPlay").text() == "Play Neverwinter\nNights"


def test_set_enabled(qtbot):
    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    ribbon.set_enabled("RbnToolset", False)
    assert not ribbon.button("RbnToolset").isEnabled()


def test_added_buttons_are_kept_out_of_the_verbatim_vb_layout():
    """"Verbatim from the designer" has to stay a claim that can be checked."""
    vb = {item.action for _, items in VB_RIBBON_TABS for item in items}
    added = {item.action for _, _, item in ADDED_BUTTONS}
    assert not (vb & added)
    assert {item.action for _, items in RIBBON_TABS for item in items} == vb | added


def test_an_added_button_sits_beside_the_one_it_follows(qtbot):
    """The PRC-ified Drive source belongs next to the Vault source it complements."""
    play = dict(RIBBON_TABS)["Play"]
    order = [item.action for item in play]
    assert order.index("RbnPrcModule") == order.index("RbnDownloadProject") + 1


def test_tabs_left_aligned(qtbot):
    """VB TbRibbon left-packs its tabs; Qt/macOS would center them otherwise."""
    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    assert not ribbon.tabBar().expanding()
    assert "alignment: left" in ribbon.styleSheet()


# -- a greyed button must mean "unported", not "unwired" ------------------------ #
def test_no_ribbon_button_is_greyed_out_for_a_screen_that_exists(qtbot):
    """Manage Steam Workshop Content was dead on the ribbon and alive on Tools.

    The ribbon and the menu carry different VB ids for the same command, so
    wiring only the menu one leaves the ribbon button disabled with "Not yet
    available in Vaultkeeper" — a working feature advertised as missing. This
    pairs the two by the screen they open, not by id.
    """
    from vaultkeeper.ui.main_window import MainWindow
    from vaultkeeper.ui.ribbon import RIBBON_TABS

    window = MainWindow(None)
    qtbot.addWidget(window)
    implemented = window.implemented_commands()
    handlers = window._command_handlers()

    unwired = []
    for _title, items in RIBBON_TABS:
        for item in items:
            if item.action in implemented:
                continue
            # Is the same screen reachable under another id? Ribbon ids are
            # "Rbn<Thing>"; the menu twin is "Ms<Thing>".
            twin = "Ms" + item.action[3:]
            if twin in handlers:
                unwired.append((item.action, twin))
    assert not unwired, (
        "these ribbon buttons are greyed out although their command is ported: "
        + ", ".join(f"{a} (wired as {b})" for a, b in unwired)
    )


def test_the_workshop_ribbon_button_opens_the_same_screen_as_the_menu(qtbot):
    from vaultkeeper.ui.main_window import MainWindow

    window = MainWindow(None)
    qtbot.addWidget(window)
    handlers = window._command_handlers()
    assert handlers["RbnManageWorkshop"] == handlers["MsWorkshopViewer"]
    assert "RbnManageWorkshop" in window.implemented_commands()


# -- right-click alternates (VB Rbn*/Ms*_MouseUp) ------------------------------- #
def test_a_ribbon_button_reports_a_right_click(qtbot):
    """Qt has no signal for it, and a behaviour with no signal cannot be wired."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from vaultkeeper.ui.ribbon import Ribbon

    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    ribbon.show()
    seen = []
    ribbon.action_right_clicked.connect(seen.append)
    button = ribbon.button("RbnPlay")
    QTest.mouseClick(button, Qt.MouseButton.RightButton)
    assert seen == ["RbnPlay"]


def test_a_left_click_is_still_an_ordinary_click(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from vaultkeeper.ui.ribbon import Ribbon

    ribbon = Ribbon()
    qtbot.addWidget(ribbon)
    ribbon.show()
    left, right = [], []
    ribbon.action_triggered.connect(left.append)
    ribbon.action_right_clicked.connect(right.append)
    QTest.mouseClick(ribbon.button("RbnPlay"), Qt.MouseButton.LeftButton)
    assert left == ["RbnPlay"] and right == []


def test_right_clicking_play_opens_the_start_screen_manager(qtbot, tmp_path):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(None)
    qtbot.addWidget(win)
    win._on_command_right_clicked("RbnPlay")  # no controller: must not raise

    opened = []
    win.controller = object()
    win._on_loadscreens = lambda: opened.append("loadscreens")
    win._on_command_right_clicked("RbnPlay")
    assert opened == ["loadscreens"]


def test_right_clicking_portrait_manager_opens_the_portrait_site(qtbot, tmp_path):
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(None)
    qtbot.addWidget(win)

    class Ctrl:
        @staticmethod
        def _settings():
            return Settings(portrait_image_web_page="https://portraits.example")

    win.controller = Ctrl()
    urls = []
    win._open_url = urls.append
    win._on_command_right_clicked("MsPortraitManager")
    assert urls == ["https://portraits.example"]


def test_with_no_portrait_site_set_it_says_so(qtbot):
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(None)
    qtbot.addWidget(win)

    class Ctrl:
        @staticmethod
        def _settings():
            return Settings(portrait_image_web_page="")

    win.controller = Ctrl()
    win._open_url = lambda url: pytest.fail("nothing to open")
    win._on_command_right_clicked("MsPortraitManager")
    assert "No portrait image web page" in win.nit_status.mg_info.text()


def test_a_command_with_no_alternate_does_nothing(qtbot):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(None)
    qtbot.addWidget(win)
    win.controller = object()
    win._on_command_right_clicked("RbnInstallUninstall")  # must not raise
