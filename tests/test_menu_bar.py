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


# -- keyboard shortcuts (VB's Keyboard Shortcuts help topic) -------------------- #
def test_the_documented_shortcuts_are_bound(qtbot):
    """The topic listed fourteen; the port had none, so it documented fiction.

    Binding is all this can check: **Qt does not deliver shortcuts under the
    offscreen platform at all** — a minimal QAction on a bare QWidget does not
    fire either — so a test that pressed the keys would be measuring the
    platform. Firing was verified on a real one, through the CrossOver bottle:
    Ctrl+G, Ctrl+L and Ctrl+R triggered their commands, and F2 correctly did
    not until a mod was selected, because Rename is selection-gated.
    """
    from PySide6.QtGui import QKeySequence

    from vaultkeeper.ui.menu_bar import SHORTCUTS

    bar = NitMenuBar()
    qtbot.addWidget(bar)
    for action_id, key in SHORTCUTS.items():
        act = bar.action(action_id)
        assert act is not None, f"{action_id} is not on the menus"
        assert act.shortcut() == QKeySequence(key), f"{action_id} should be {key}"


def test_every_shortcut_names_a_real_command(qtbot):
    """A key bound to an id that does not exist is a key that does nothing."""
    from vaultkeeper.ui.menu_bar import SHORTCUTS

    bar = NitMenuBar()
    qtbot.addWidget(bar)
    unknown = [a for a in SHORTCUTS if bar.action(a) is None]
    assert not unknown, f"shortcuts for commands that do not exist: {unknown}"


def test_no_two_commands_share_a_key(qtbot):
    from vaultkeeper.ui.menu_bar import SHORTCUTS

    keys = list(SHORTCUTS.values())
    assert len(keys) == len(set(keys)), "two commands claim the same shortcut"


def test_the_shortcuts_match_the_original(qtbot):
    """Spot-checked against the help topic's own table."""
    from vaultkeeper.ui.menu_bar import SHORTCUTS

    assert SHORTCUTS["MsCreateInstaller"] == "Ctrl+L"
    assert SHORTCUTS["MsNewGroup"] == "Ctrl+G"
    assert SHORTCUTS["MsNewMod"] == "Ctrl+M"
    assert SHORTCUTS["MsModExplorer"] == "Ctrl+R"
    assert SHORTCUTS["MsCopyName"] == "Ctrl+Alt+C"
    assert SHORTCUTS["MsRename"] == "F2"


def test_the_window_owns_the_shortcut_actions(qtbot):
    """In scope from the start, rather than once the window has been clicked."""
    from vaultkeeper.ui.main_window import MainWindow
    from vaultkeeper.ui.menu_bar import SHORTCUTS

    win = MainWindow(None)
    qtbot.addWidget(win)
    owned = {a.text() for a in win.actions()}
    for action_id in SHORTCUTS:
        assert win.nit_menu.action(action_id).text() in owned, action_id
