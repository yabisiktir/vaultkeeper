"""Tests for the app-level PlayLoop composition (Phase 5 wired end-to-end)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.ui.play_loop import PlayLoop


def _setup(tmp_path: Path) -> PlayLoop:
    profile_mods = tmp_path / "Profiles" / "P"
    (tmp_path / "Data").mkdir(parents=True, exist_ok=True)
    logs = tmp_path / "user" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "nwclientlog1.txt").write_text(
        "\n".join(
            [
                "[Mon Nov 02 17:00:00] Loading Module: Aielund Saga",
                "[Mon Nov 02 17:30:00] Loading Module: Swordflight",
                "[Mon Nov 02 18:00:00] Server Shutting Down",
            ]
        ),
        encoding="utf-8",
    )
    pd = ProfileData()
    return PlayLoop(
        pd,
        profile_mods_dir=profile_mods,
        data_dir=tmp_path / "Data",
        saves_dir=tmp_path / "user" / "saves",
        log_path=logs / "nwclientlog1.txt",
    )


def test_process_session_attributes_time(tmp_path):
    loop = _setup(tmp_path)
    summary = loop.process_session(
        datetime(2020, 11, 2, 16, 59), datetime(2020, 11, 2, 18, 1)
    )
    assert summary["mods"]["Aielund Saga"] == timedelta(minutes=30)
    assert summary["mods"]["Swordflight"] == timedelta(minutes=30)
    assert loop.play_time("Aielund Saga") == timedelta(minutes=30)
    assert loop.total_played == timedelta(hours=1)


def test_process_session_persists_play_data(tmp_path):
    loop = _setup(tmp_path)
    loop.process_session(datetime(2020, 11, 2, 16, 59), datetime(2020, 11, 2, 18, 1))
    # A fresh PlayLoop over the same data dir reloads the recorded times.
    loop2 = _setup(tmp_path)
    assert loop2.play_time("Aielund Saga") == timedelta(minutes=30)


def test_no_log_file_records_execution_only(tmp_path):
    loop = _setup(tmp_path)
    loop.log_path = tmp_path / "user" / "logs" / "missing.txt"
    summary = loop.process_session(
        datetime(2020, 11, 2, 17, 0), datetime(2020, 11, 2, 18, 0)
    )
    assert summary["mods"] == {}
    assert summary["execution_time"] == timedelta(hours=1)
    assert loop.total_played == timedelta(hours=1)


def test_game_saves_summary_no_saves(tmp_path):
    loop = _setup(tmp_path)
    assert "No games" in loop.current_game_summary()


def test_game_saves_scans_real_folder(tmp_path):
    loop = _setup(tmp_path)
    saves = tmp_path / "user" / "saves"
    d = saves / "000002 - birr"
    d.mkdir(parents=True)
    (d / "Aielund Saga.sav").write_bytes(b"\x00" * 8)
    (d / "savenfo.txt").write_text("Beorunna's Well", encoding="utf-8")
    gs = loop.game_saves()
    assert gs.count == 1
    assert gs.current_game_save == "Aielund Saga"


def test_start_dates_recorded(tmp_path):
    loop = _setup(tmp_path)
    loop.process_session(datetime(2020, 11, 2, 16, 59), datetime(2020, 11, 2, 18, 1))
    # Logged (non-path) module names record a first-seen start date.
    assert loop.play_data.start_date("Aielund Saga") is not None
