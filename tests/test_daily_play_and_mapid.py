"""Item 8 — Copy MapId Rule (WorkshopViewer) + DailyPlayTime auto day factor."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vaultkeeper.game.daily_play_time import (
    DailyPlayTime,
    session_minutes,
)
from vaultkeeper.game.workshop import MAP_ID_TEXT, map_id_rule
from vaultkeeper.ui.controller import ProfileController


# -- Copy MapId Rule ------------------------------------------------------- #
def test_map_id_rule_format():
    assert MAP_ID_TEXT == "MapId "
    assert map_id_rule("704450", "Cool Mod") == "MapId 704450 = Cool Mod"


def test_workshop_viewer_copy_map_id(tmp_path, qtbot):
    from PySide6.QtWidgets import QApplication, QTreeWidgetItem

    from vaultkeeper.ui.dialogs.workshop_viewer import WorkshopViewer

    ctrl = _controller(tmp_path)
    dlg = WorkshopViewer(ctrl)
    qtbot.addWidget(dlg)
    # Inject a selectable row (block signals so _on_selection's row lookup is skipped).
    dlg.items.blockSignals(True)
    dlg.items.clear()
    dlg.items.addTopLevelItem(QTreeWidgetItem(["704450", "No", "Cool Mod"]))
    dlg.items.setCurrentItem(dlg.items.topLevelItem(0))
    dlg.items.blockSignals(False)
    dlg._on_copy_map_id_rule()
    assert QApplication.clipboard().text() == "MapId 704450 = Cool Mod"


# -- DailyPlayTime --------------------------------------------------------- #
def test_session_minutes():
    a = datetime(2026, 7, 16, 10, 0, 0)
    b = datetime(2026, 7, 16, 11, 30, 0)
    assert session_minutes(a, b) == 90
    assert session_minutes(b, a) == 0  # never negative


def test_daily_average_and_info():
    d = DailyPlayTime()
    d.add(120, day="2026-07-14")  # 2 h
    d.add(60, day="2026-07-15")  # 1 h
    d.add(30, day="2026-07-16")  # today (excluded from average)
    avg = d.daily_average_hours(today="2026-07-16")
    assert avg == 2  # round((120+60)/2 / 60) = round(1.5) = 2
    info = d.daily_play_info()
    assert info[0]["date"] == "2026-07-16"  # most recent first
    assert info[0]["label"] == "30 mins"


def test_daily_average_single_day_and_floor():
    assert DailyPlayTime().daily_average_hours() == 1  # nothing recorded -> 1
    only_today = DailyPlayTime({"2026-07-16": 200})
    # Only one day recorded -> that day's hours (200 min = 3 h).
    assert only_today.daily_average_hours(today="2026-07-16") == 3


def test_daily_play_time_json_round_trip():
    d = DailyPlayTime({"2026-07-16": 45})
    assert DailyPlayTime.from_json(d.to_json()).minutes_by_date == {"2026-07-16": 45}
    assert DailyPlayTime.from_json("garbage").minutes_by_date == {}


# -- controller ------------------------------------------------------------ #
def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_record_daily_play_and_report(tmp_path):
    ctrl = _controller(tmp_path)
    ctrl.record_daily_play(120, day="2026-07-14")
    ctrl.record_daily_play(60, day="2026-07-14")  # accumulates same day -> 180
    report = ctrl.daily_play_report()
    assert report["recorded"] is True
    assert any(r["date"] == "2026-07-14" and r["minutes"] == 180 for r in report["days"])


def test_process_session_records_daily(tmp_path):
    ctrl = _controller(tmp_path)
    a = datetime(2026, 7, 16, 10, 0, 0)
    b = datetime(2026, 7, 16, 12, 0, 0)  # 120 min
    ctrl.process_play_session(a, b)
    daily = ctrl._load_daily_play_time()
    assert daily.minutes_by_date.get("2026-07-16") == 120


def test_play_data_viewer_shows_daily_average(tmp_path, qtbot):
    from PySide6.QtWidgets import QLabel

    from vaultkeeper.ui.dialogs.play_data_viewer import PlayDataViewer

    ctrl = _controller(tmp_path)
    ctrl.record_daily_play(180, day="2026-07-14")
    dlg = PlayDataViewer.show_for(ctrl)
    qtbot.addWidget(dlg)
    labels = [w.text() for w in dlg.findChildren(QLabel)]
    assert any("Average per day" in t for t in labels)
