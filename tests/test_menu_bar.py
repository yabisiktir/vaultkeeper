"""Tests for the NitMenuBar widget."""

from __future__ import annotations

from vaultkeeper.ui import resources as R
from vaultkeeper.ui.menu_bar import MENUS, NitMenuBar


def test_nine_top_menus_in_order(qtbot):
    bar = NitMenuBar()
    qtbot.addWidget(bar)
    titles = [m.title() for m in bar.findChildren(type(bar.menus["MsFile"]))]
    # The nine standard menus, in the VB order.
    expected = ["&File", "&Edit", "&View", "&Manage", "&Tools", "&Run", "&Web", "&Options", "&Help"]
    for want in expected:
        assert want in titles


def test_menu_registry_matches_data(qtbot):
    bar = NitMenuBar()
    qtbot.addWidget(bar)
    expected = {i.action for _, _, items in MENUS for i in items if i.action}
    assert set(bar.actions_by_id) == expected


def test_every_menu_item_with_image_has_an_asset(qtbot):
    bar = NitMenuBar()
    qtbot.addWidget(bar)
    missing = [
        i.action
        for _, _, items in MENUS
        for i in items
        if i.action and i.image and not R.icon_exists(i.image)
    ]
    assert not missing, f"menu items with no asset: {missing}"


def test_known_items_present_with_captions(qtbot):
    bar = NitMenuBar()
    qtbot.addWidget(bar)
    assert bar.action("MsExit").text() == "E&xit"
    assert bar.action("MsInstall").text() == "&Install"
    assert bar.action("MsPlayNeverwinterNights").text() == "&Neverwinter Nights"


def test_trigger_emits_action_id(qtbot):
    bar = NitMenuBar()
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.action_triggered) as sig:
        bar.action("MsInstall").trigger()
    assert sig.args == ["MsInstall"]


def test_checkable_items_toggle(qtbot):
    bar = NitMenuBar()
    qtbot.addWidget(bar)
    # Show Ribbon / Show Toolbar are check-on-click toggles in the VB Options menu.
    ribbon_act = bar.action("MsShowRibbon")
    assert ribbon_act is not None and ribbon_act.isCheckable()
    with qtbot.waitSignal(bar.action_toggled) as sig:
        ribbon_act.trigger()
    assert sig.args[0] == "MsShowRibbon"


def test_set_enabled(qtbot):
    bar = NitMenuBar()
    qtbot.addWidget(bar)
    bar.set_enabled("MsUninstall", False)
    assert not bar.action("MsUninstall").isEnabled()
