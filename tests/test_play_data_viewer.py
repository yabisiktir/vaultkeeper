"""Tests for the play-time report + viewer dialog."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.play_data_viewer import PlayDataViewer


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    for name in ("Alpha", "Beta"):
        f = profile_mods / name / C.MOD_INSTALLER_DIR / "hak" / "x.hak"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_report_sorts_by_time_desc(qtbot, tmp_path):
    controller = _controller(tmp_path)
    loop = controller.play_loop
    loop.play_data.pdi.play_times["Alpha"] = timedelta(hours=2)
    loop.play_data.pdi.play_times["Beta"] = timedelta(hours=10)
    loop.play_data.pdi.total_played = timedelta(hours=12)
    loop.play_data.set_start_date("Beta", datetime(2020, 1, 5))

    report = controller.play_times_report()
    assert [r["mod"] for r in report["rows"]] == ["Beta", "Alpha"]
    assert report["rows"][0]["time"] == "10 hours"
    assert report["rows"][0]["started"] == "05 Jan 2020"
    assert "hour" in report["total_played"]


def test_viewer_populates_table(qtbot, tmp_path):
    controller = _controller(tmp_path)
    loop = controller.play_loop
    loop.play_data.pdi.play_times["Alpha"] = timedelta(hours=3, minutes=20)
    loop.play_data.pdi.total_played = timedelta(hours=3, minutes=20)

    dlg = PlayDataViewer.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 1
    item = dlg.table.topLevelItem(0)
    assert item.text(0) == "Alpha"
    assert item.text(1) == "3 hours 20 mins"


def test_report_empty_when_no_play_data(qtbot, tmp_path):
    controller = _controller(tmp_path)
    report = controller.play_times_report()
    assert report["rows"] == []
