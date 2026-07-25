"""Tests for the ModPlayViewer report (controller) and dialog population.

Covers VB ``ModPlayViewer``: only mods with a module file appear, ordered from
the oldest last-completed date, each carrying the current user's completed/play
time and its per-user play-time history.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.core.rtf import write_rtf  # noqa: E402
from vaultkeeper.game.play_data_manager import _current_user  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.mod_play_viewer import ModPlayViewer  # noqa: E402


def _write_play_time(profile_mods: Path, mod: str, completed: str, played: str) -> None:
    """Write a single-record ``.Game Play Time.rtf`` for the current OS user."""
    line = f"{completed:<20}{played:<25}{_current_user()}"
    path = profile_mods / mod / C.PLAY_TIME_FILE
    path.write_text(write_rtf([line]), encoding="utf-8")


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    # Three mods with a module file (appear), one hak-only mod (excluded).
    for name in ("Alpha", "Beta", "Gamma"):
        f = profile_mods / name / C.MOD_INSTALLER_DIR / C.MOD_FOLDER / f"{name}.mod"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"m")
    hak = profile_mods / "HakOnly" / C.MOD_INSTALLER_DIR / "hak" / "x.hak"
    hak.parent.mkdir(parents=True, exist_ok=True)
    hak.write_bytes(b"h")
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_report_only_includes_module_mods(tmp_path):
    controller = _controller(tmp_path)
    report = controller.mod_play_report()
    assert {r["mod"] for r in report["rows"]} == {"Alpha", "Beta", "Gamma"}
    assert "HakOnly" not in {r["mod"] for r in report["rows"]}


def test_report_orders_oldest_completed_first(tmp_path):
    controller = _controller(tmp_path)
    profile_mods = controller.ctx.profile_mods_dir
    # Alpha stays unplayed (sorts first); Beta older than Gamma.
    _write_play_time(profile_mods, "Beta", "10 Feb 2019", "2 hours 30 mins")
    _write_play_time(profile_mods, "Gamma", "05 Jan 2020", "5 hours")

    report = controller.mod_play_report()
    assert [r["mod"] for r in report["rows"]] == ["Alpha", "Beta", "Gamma"]

    alpha = report["rows"][0]
    assert alpha["completed"] == ""
    assert alpha["play_time"] == "None Recorded"

    gamma = report["rows"][2]
    assert gamma["completed"] == "05 Jan 2020"
    assert gamma["play_time"] == "5 hrs"  # "hours" -> "hrs"
    assert gamma["play_times"] == [
        {"completed": "05 Jan 2020", "play_time": "5 hours", "user": _current_user()}
    ]


def test_report_summary_counts(tmp_path):
    controller = _controller(tmp_path)
    report = controller.mod_play_report()
    assert report["total"] == 3
    # Nothing is installed into the (empty) game folder.
    assert report["summary"] == f"{report['installed']}/3"


def test_dialog_populates_and_selects_first(qtbot, tmp_path):
    controller = _controller(tmp_path)
    _write_play_time(controller.ctx.profile_mods_dir, "Gamma", "05 Jan 2020", "5 hours")

    dlg = ModPlayViewer.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.mods.topLevelItemCount() == 3
    # First row selected on open, detail pane populated.
    first = dlg.mods.topLevelItem(0)
    assert dlg.mods.currentItem() is first
    assert dlg.group_label.text().startswith("Group:")

    # Selecting Gamma shows its play-time history row.
    for i in range(dlg.mods.topLevelItemCount()):
        if dlg.mods.topLevelItem(i).text(0) == "Gamma":
            dlg.mods.setCurrentItem(dlg.mods.topLevelItem(i))
            break
    assert dlg.times.topLevelItemCount() == 1
    assert dlg.times.topLevelItem(0).text(0) == "05 Jan 2020"
    assert dlg.times.topLevelItem(0).text(2) == _current_user()


# -- Filter toolbar (VB group / only-completed options) -------------------- #


def test_dialog_group_include_exclude_filter(qtbot):
    # VB CommonFiltersDialogue: multi-group include/exclude (not a single combo).
    report = {
        "rows": [
            {"mod": "A", "completed": "01 Jan 2024", "play_time": "1h", "rating": "",
             "start": "", "end": "", "state": -2, "group": "RPG",
             "web_link": "", "best_weapon": "", "played_info": "", "notes": "",
             "play_times": []},
            {"mod": "B", "completed": "", "play_time": "", "rating": "",
             "start": "", "end": "", "state": -2, "group": "Puzzle",
             "web_link": "", "best_weapon": "", "played_info": "", "notes": "",
             "play_times": []},
        ],
        "summary": "0/2",
    }
    dlg = ModPlayViewer(report)
    qtbot.addWidget(dlg)
    assert dlg.mods.topLevelItemCount() == 2
    # Exclude the Puzzle group (uncheck it).
    dlg._group_filters["Puzzle"] = False
    dlg._populate_mods()
    assert dlg.mods.topLevelItemCount() == 1
    assert dlg.mods.topLevelItem(0).text(0) == "A"
    # Only-completed filter (re-include all groups first).
    dlg._group_filters = {g: True for g in dlg._groups}
    dlg.only_completed.setChecked(True)
    assert dlg.mods.topLevelItemCount() == 1  # only A has a completed date
    assert dlg.mods.topLevelItem(0).text(0) == "A"


def test_dialog_rating_filter(qtbot):
    # The rating filter was entirely missing before (CommonFiltersDialogue thin-out).
    report = {
        "rows": [
            {"mod": "Great", "completed": "", "play_time": "", "rating": "Excellent",
             "start": "", "end": "", "state": -2, "group": "RPG",
             "web_link": "", "best_weapon": "", "played_info": "", "notes": "",
             "play_times": []},
            {"mod": "Meh", "completed": "", "play_time": "", "rating": "Poor",
             "start": "", "end": "", "state": -2, "group": "RPG",
             "web_link": "", "best_weapon": "", "played_info": "", "notes": "",
             "play_times": []},
        ],
        "summary": "0/2",
    }
    dlg = ModPlayViewer(report)
    qtbot.addWidget(dlg)
    assert dlg.mods.topLevelItemCount() == 2
    dlg._rating_filters["Poor"] = False  # exclude Poor-rated mods
    dlg._populate_mods()
    assert dlg.mods.topLevelItemCount() == 1
    assert dlg.mods.topLevelItem(0).text(0) == "Great"


def test_common_filters_dialog_round_trip(qtbot):
    from PySide6.QtCore import Qt

    from vaultkeeper.ui.dialogs.common_filters import CommonFiltersDialog

    dlg = CommonFiltersDialog(
        ["RPG", "Puzzle"], ["Excellent", "Poor"],
        {"RPG": True, "Puzzle": False}, {"Excellent": True, "Poor": True},
    )
    qtbot.addWidget(dlg)
    # Initial check state reflects the passed-in include dicts.
    assert dlg.group_filters() == {"RPG": True, "Puzzle": False}
    # Clear All excludes everything.
    dlg._set_all(Qt.CheckState.Unchecked)
    assert not any(dlg.group_filters().values())
    assert not any(dlg.rating_filters().values())


def test_dialog_min_end_level_filter(qtbot):
    report = {
        "rows": [
            {"mod": "Low", "completed": "", "play_time": "", "rating": "",
             "start": "", "end": "12", "state": -2, "group": "RPG",
             "web_link": "", "best_weapon": "", "played_info": "", "notes": "",
             "play_times": []},
            {"mod": "High", "completed": "", "play_time": "", "rating": "",
             "start": "", "end": "40", "state": -2, "group": "RPG",
             "web_link": "", "best_weapon": "", "played_info": "", "notes": "",
             "play_times": []},
        ],
        "summary": "0/2",
    }
    dlg = ModPlayViewer(report)
    qtbot.addWidget(dlg)
    assert dlg.mods.topLevelItemCount() == 2
    dlg.min_end.setText("20")  # only the level-40 mod qualifies
    assert dlg.mods.topLevelItemCount() == 1
    assert dlg.mods.topLevelItem(0).text(0) == "High"
