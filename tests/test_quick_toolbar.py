"""Tests for the QuickToolbar widget."""

from __future__ import annotations

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.quick_toolbar import QUICK_ITEMS, QuickToolbar


def test_all_buttons_present(qtbot):
    tb = QuickToolbar()
    qtbot.addWidget(tb)
    expected = {i.action for i in QUICK_ITEMS if i.action}
    assert set(tb.actions_by_id) == expected


def test_every_button_has_a_real_icon(qtbot):
    tb = QuickToolbar()
    qtbot.addWidget(tb)
    missing = [i.action for i in QUICK_ITEMS if i.action and not R.icon_exists(i.image)]
    assert not missing, f"toolbar buttons with no asset: {missing}"


def test_click_emits_action_id(qtbot):
    tb = QuickToolbar()
    qtbot.addWidget(tb)
    with qtbot.waitSignal(tb.action_triggered) as sig:
        tb.actions_by_id["TsInstall"].trigger()
    assert sig.args == ["TsInstall"]


def test_separators_included(qtbot):
    tb = QuickToolbar()
    qtbot.addWidget(tb)
    # The toolbar has more QAction slots than buttons (separators are actions too).
    sep_count = sum(1 for i in QUICK_ITEMS if not i.action)
    assert len(tb.actions()) == len(tb.actions_by_id) + sep_count


def test_set_enabled(qtbot):
    tb = QuickToolbar()
    qtbot.addWidget(tb)
    tb.set_enabled("TsPlayNeverwinterNights", False)
    assert not tb.actions_by_id["TsPlayNeverwinterNights"].isEnabled()
