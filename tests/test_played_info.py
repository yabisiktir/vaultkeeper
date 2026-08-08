"""The menu bar's play-time readout (VB ``Defs.TitleInfo`` / ``MsPlayedInfo``).

This reports the **game**, not the selected mod. The port had it the other way
round, so it was blank unless you happened to click a mod with recorded time —
which is why the owner could see "Total time played" in the original's
screenshots and find no way to turn it on. VB is never blank once a profile is
open; each branch below is one of its states.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.core.formatting import to_date_string  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.main_window import MainWindow  # noqa: E402


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    (profile_mods / "Adventure" / C.MOD_INSTALLER_DIR).mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.ctx.game_user_dir = tmp_path / "gameuser"
    (tmp_path / "gameuser" / "saves").mkdir(parents=True)
    return controller


def _pdm(controller):
    return controller.play_loop.play_data


class TestTheStates:
    def test_nothing_ever_played(self, tmp_path):
        controller = _controller(tmp_path)
        assert controller.play_time_info()["text"] == "NWN not played"

    def test_the_total_when_there_is_nothing_more_pressing_to_say(self, tmp_path):
        """The state the owner saw in the original and could not find here."""
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.pdi.total_played = timedelta(hours=128)
        pdm.pdi.last_played = to_date_string(datetime.now())
        text = controller.play_time_info()["text"]
        assert text.startswith("Total time played:")
        assert "128 hours" in text

    def test_played_today(self, tmp_path):
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.pdi.total_played = timedelta(hours=5)
        pdm.pdi.total_today = timedelta(minutes=45)
        assert controller.play_time_info()["text"] == "Played for 45 mins today"

    def test_not_played_for_a_while(self, tmp_path):
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.pdi.total_played = timedelta(hours=5)
        pdm.pdi.last_played = to_date_string(datetime.now() - timedelta(days=9))
        assert controller.play_time_info()["text"] == "Not played for 9 days"

    def test_a_game_in_progress_reports_its_own_time(self, tmp_path):
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.settings.play_time_mod = "Adventure"
        pdm.pdi.play_times["Adventure"] = timedelta(hours=3, minutes=20)
        text = controller.play_time_info()["text"]
        assert text == "Played for 3 hours 20 mins"

    def test_a_game_in_progress_with_no_time_yet(self, tmp_path):
        controller = _controller(tmp_path)
        _pdm(controller).settings.play_time_mod = "Adventure"
        assert controller.play_time_info()["text"] == "Mod play time unknown"

    def test_a_corrupt_last_played_date_says_so_rather_than_raising(self, tmp_path):
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.pdi.total_played = timedelta(hours=5)
        pdm.pdi.last_played = "not a date"
        assert controller.play_time_info()["text"] == "Last played date corrupted"


class TestTheTooltip:
    def test_it_always_carries_the_daily_average(self, tmp_path):
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.pdi.total_played = timedelta(hours=5)
        pdm.pdi.last_played = to_date_string(datetime.now())
        tip = controller.play_time_info()["tooltip"]
        assert "Average Play Time per Day:" in tip
        assert "Play Time Hours per Day:" in tip

    def test_a_game_in_progress_says_when_it_started_and_how_often(self, tmp_path):
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.settings.play_time_mod = "Adventure"
        pdm.pdi.play_times["Adventure"] = timedelta(hours=2)
        pdm.set_start_date("Adventure", datetime.now())
        tip = controller.play_time_info()["tooltip"]
        assert "Started Today" in tip
        assert "1st time" in tip

    def test_a_long_total_is_also_spelled_out_in_days(self, tmp_path):
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.pdi.total_played = timedelta(days=9)
        pdm.pdi.last_played = to_date_string(datetime.now())
        assert "day" in controller.play_time_info()["tooltip"].lower()


class TestTheMenuBar:
    def test_it_is_populated_the_moment_a_profile_opens(self, qtbot, tmp_path):
        """It used to stay blank until a mod with recorded time was clicked."""
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.pdi.total_played = timedelta(hours=42)
        pdm.pdi.last_played = to_date_string(datetime.now())
        win = MainWindow(controller)
        qtbot.addWidget(win)
        win.refresh()
        assert "Total time played" in win._played_info.text()
        assert win._played_info.toolTip()

    def test_it_does_not_change_with_the_selection(self, qtbot, tmp_path):
        """The readout is about the game; the selection is a different question."""
        controller = _controller(tmp_path)
        pdm = _pdm(controller)
        pdm.pdi.total_played = timedelta(hours=42)
        pdm.pdi.last_played = to_date_string(datetime.now())
        win = MainWindow(controller)
        qtbot.addWidget(win)
        win._update_played_info("Adventure")
        selected = win._played_info.text()
        win._update_played_info(None)
        assert win._played_info.text() == selected

    def test_no_profile_means_no_readout(self, qtbot):
        win = MainWindow(None)
        qtbot.addWidget(win)
        win._update_played_info()
        assert win._played_info.text() == ""
