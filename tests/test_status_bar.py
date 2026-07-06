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
