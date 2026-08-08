"""Tests for the NitStatusBar widget."""

from __future__ import annotations

from vaultkeeper.ui.status_bar import (
    SELECT_HISTORY,
    SELECT_PLAY_TIME,
    NitStatusBar,
)


def test_segments_present_with_defaults(qtbot):
    bar = NitStatusBar()
    qtbot.addWidget(bar)
    assert bar.bt_mods.text() == "Mods:"
    assert bar.bt_mod_count.text() == "0/0"
    assert bar.bt_group.text() == "None"
    # Icon buttons carry real (non-null) images.
    assert not bar.bt_character.icon().isNull()
    assert not bar.bt_recycle.icon().isNull()


def test_conditional_segments_hidden_by_default(qtbot):
    bar = NitStatusBar()
    qtbot.addWidget(bar)
    assert not bar.bt_file_check.isVisible()
    assert not bar.bt_health.isVisible()
    assert not bar.bt_wizard.isVisible()


def test_mod_count_and_group_setters(qtbot):
    bar = NitStatusBar()
    qtbot.addWidget(bar)
    bar.set_mod_count(3, 7)
    assert bar.bt_mod_count.text() == "3/7"
    bar.set_group("Adventures")
    assert bar.bt_group.text() == "Adventures"
    bar.set_group("")
    assert bar.bt_group.text() == "None"


def test_recycle_toggle_signal_and_image(qtbot):
    bar = NitStatusBar()
    qtbot.addWidget(bar)
    assert bar.recycle is True
    with qtbot.waitSignal(bar.recycle_toggled) as sig:
        bar.bt_recycle.click()
    assert sig.args == [False]
    assert bar.recycle is False


def test_overwrite_toggle_signal(qtbot):
    bar = NitStatusBar()
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.overwrite_toggled) as sig:
        bar.bt_overwrite.click()
    assert sig.args == [False]
    assert bar.overwrite is False


def test_select_state_cycle(qtbot):
    bar = NitStatusBar()
    qtbot.addWidget(bar)
    bar.set_select_state(SELECT_PLAY_TIME)
    assert bar.select_state == SELECT_PLAY_TIME
    assert "Play Time" in bar.bt_select_file.toolTip()
    bar.set_select_state(SELECT_HISTORY)
    assert bar.select_state == SELECT_HISTORY
    bar.set_select_state("bogus")  # ignored
    assert bar.select_state == SELECT_HISTORY


def test_mods_click_signal(qtbot):
    bar = NitStatusBar()
    qtbot.addWidget(bar)
    with qtbot.waitSignal(bar.mods_clicked):
        bar.bt_mods.click()


def test_info_setter(qtbot):
    bar = NitStatusBar()
    qtbot.addWidget(bar)
    bar.set_info("Installed 3 files")
    assert bar.mg_info.text() == "Installed 3 files"


# -- the icons were dead to the click ------------------------------------------- #
def test_a_status_icon_reports_a_right_click(qtbot):
    """Each carries a second, related screen on the right button (VB Bt*_MouseUp)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    bar = NitStatusBar()
    qtbot.addWidget(bar)
    bar.show()
    seen = []
    bar.character_right_clicked.connect(lambda: seen.append("character"))
    QTest.mouseClick(bar.bt_character, Qt.MouseButton.RightButton)
    assert seen == ["character"]


def test_a_left_click_still_reaches_the_ordinary_signal(qtbot):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    bar = NitStatusBar()
    qtbot.addWidget(bar)
    bar.show()
    left, right = [], []
    bar.character_clicked.connect(lambda: left.append(1))
    bar.character_right_clicked.connect(lambda: right.append(1))
    QTest.mouseClick(bar.bt_character, Qt.MouseButton.LeftButton)
    assert left == [1] and right == []


def test_every_clickable_icon_is_connected_to_something(qtbot):
    """Every one but Mods emitted into the void: the icons did nothing at all.

    Their tooltips promised otherwise — the pending-changes icon says it will
    "display details about files added, removed or changed", and clicking it
    did nothing whatsoever.
    """
    from PySide6.QtCore import QMetaMethod

    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(None)
    qtbot.addWidget(win)
    bar = win.nit_status
    unconnected = [
        name
        for name in (
            "mods_clicked",
            "group_clicked",
            "info_clicked",
            "wizard_clicked",
            "character_clicked",
            "health_clicked",
            "file_check_clicked",
            "character_right_clicked",
            "wizard_right_clicked",
            "select_file_right_clicked",
            "recycle_right_clicked",
        )
        if not bar.isSignalConnected(QMetaMethod.fromSignal(getattr(bar, name)))
    ]
    assert not unconnected, f"status-bar signals nothing listens to: {unconnected}"
