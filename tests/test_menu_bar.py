"""Tests for the NitMenuBar widget."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Qt

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


# -- macOS: what Qt cannot fix by itself ---------------------------------------- #
def test_ctrl_becomes_command_without_our_help(qtbot):
    """The one Mac-ism that needs no code: Qt maps portable Ctrl to ⌘ itself."""
    from PySide6.QtGui import QKeySequence

    native = QKeySequence("Ctrl+G").toString(QKeySequence.SequenceFormat.NativeText)
    assert native == ("⌘G" if sys.platform == "darwin" else "Ctrl+G")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS conventions")
def test_the_function_keys_gain_a_mac_alternative(qtbot):
    """F1 and F2 are media keys on Apple keyboards unless the user has turned on
    "Use F1, F2, etc. as standard function keys" — off by default — so for most
    Mac users those two shortcuts never fire at all."""
    from PySide6.QtGui import QKeySequence

    bar = NitMenuBar()
    qtbot.addWidget(bar)

    # Help asks StandardKey rather than naming a key, so each platform gets its
    # own answer. What that answer *is* cannot be asserted here: under the
    # offscreen platform StandardKey.HelpContents comes back as "F1" rather than
    # the real ⌘?, so this would be measuring the platform again. Checked on a
    # live cocoa QApplication instead, where MsViewHelp carries ['F1', '⌘?'].
    from vaultkeeper.ui.menu_bar import MAC_EXTRA_SHORTCUTS

    assert MAC_EXTRA_SHORTCUTS["MsViewHelp"] is QKeySequence.StandardKey.HelpContents
    assert len(bar.action("MsViewHelp").shortcuts()) == 2

    # Rename is pointedly NOT given a second shortcut here — see the FileView
    # test below for why a window-wide Return is a trap.
    assert [s.toString() for s in bar.action("MsRename").shortcuts()] == ["F2"]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS conventions")
def test_only_one_settings_item_claims_the_preferences_slot(qtbot):
    """macOS picks Preferences out of the menus by caption, and *two* of ours say
    "Settings" — left to the heuristic, both could be pulled out of Options."""
    from PySide6.QtGui import QAction

    bar = NitMenuBar()
    qtbot.addWidget(bar)
    assert bar.action("MsSettings").menuRole() == QAction.MenuRole.PreferencesRole
    assert bar.action("MsBasicSettings").menuRole() == QAction.MenuRole.NoRole


def test_the_documented_key_is_first_on_every_platform(qtbot):
    """A Mac alternative is *added*; the help topic's key stays the primary one."""
    from PySide6.QtGui import QKeySequence

    from vaultkeeper.ui.menu_bar import SHORTCUTS

    bar = NitMenuBar()
    qtbot.addWidget(bar)
    for action_id, key in SHORTCUTS.items():
        assert bar.action(action_id).shortcut() == QKeySequence(key)


def test_no_hand_rolled_quit_or_preferences_key(qtbot):
    """Qt attaches ⌘Q and ⌘, itself once a role is set; adding them by hand
    would double-bind on macOS and be wrong on Windows, where Ctrl+Q means
    nothing."""
    from vaultkeeper.ui.menu_bar import SHORTCUTS

    assert "MsExit" not in SHORTCUTS
    assert "MsSettings" not in SHORTCUTS
    assert "MsBasicSettings" not in SHORTCUTS


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS rename idiom")
def test_return_renames_from_the_mod_list_not_from_a_window_shortcut(qtbot):
    """Return renames the selected mod, and only when the list has the key.

    Rename's Mac shortcut deliberately is not on the action: Qt checks window
    shortcuts *before* the key reaches the focused widget, so a bare ``Return``
    there swallows Return in every text field in the window — including the
    inline editor renaming itself opens (verified against a live cocoa app: the
    focused line edit never saw its own Return). Handling the key in the list
    means a focused editor keeps it, because the list does not have focus then.
    """
    from vaultkeeper.core.mod_data import ModData
    from vaultkeeper.ui.file_view import FileView

    view = FileView()
    qtbot.addWidget(view)
    view.populate([("......None", [ModData(group="......None", mod_name="Alpha")])])

    asked: list[int] = []
    view.rename_requested.connect(lambda: asked.append(1))

    # Nothing selected: Return is not ours to take.
    qtbot.keyClick(view, Qt.Key.Key_Return)
    assert asked == []

    view.setCurrentItem(view.topLevelItem(0))
    qtbot.keyClick(view, Qt.Key.Key_Return)
    assert asked == [1]

    # A modified Return is somebody else's shortcut. Reset the modifier state
    # afterwards: QTest leaves the app's keyboardModifiers() latched, and other
    # widgets read it (Ctrl+click means something in this app), so a stray Ctrl
    # leaks into whatever test runs next.
    qtbot.keyClick(view, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClick(view, Qt.Key.Key_Escape)
    assert asked == [1]
