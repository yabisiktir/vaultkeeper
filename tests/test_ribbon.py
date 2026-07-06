"""Tests for the Ribbon widget."""

from __future__ import annotations

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.ribbon import RIBBON_TABS, Ribbon


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
