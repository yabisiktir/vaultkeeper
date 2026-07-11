"""Tests for the pending-play-data report + PlayDataViewPending dialog."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.core.play_time import PlayTimeInfo  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.play_data_view_pending import PlayDataViewPending  # noqa: E402


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


def test_pending_report_lists_records(tmp_path):
    controller = _controller(tmp_path)
    pdm = controller.play_loop.play_data
    pdm.pending_play_times["Mystery Mod"] = [
        PlayTimeInfo(completed="01 Jan 2024", play_time="2 hours", user_name="sam")
    ]
    report = controller.pending_play_report()
    assert report["count"] == 1
    assert report["rows"][0]["mod"] == "Mystery Mod"
    assert report["rows"][0]["play_time"] == "2 hours"


def test_pending_report_empty(tmp_path):
    assert _controller(tmp_path).pending_play_report() == {"rows": [], "count": 0}


def test_pending_dialog_populates(qtbot):
    report = {
        "rows": [
            {"mod": "A", "completed": "01 Jan", "play_time": "1 hour", "user": "u"},
            {"mod": "B", "completed": "02 Jan", "play_time": "30 mins", "user": "u"},
        ],
        "count": 2,
    }
    dlg = PlayDataViewPending(report)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 2
    assert "Pending records: 2" in dlg.summary.text()
