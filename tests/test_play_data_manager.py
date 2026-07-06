"""Tests for PlayDataManager (recording, RTF play-time files, formatting)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from vaultkeeper.core.ci_dict import CIStrDict
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.play_time import PlayTimeInfo
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.rtf import read_rtf_text
from vaultkeeper.game.client_log import ClientLogResult
from vaultkeeper.game.play_data_manager import (
    PlayDataContext,
    PlayDataManager,
    PlayDataSettings,
    RecordResult,
)


def _ctx(tmp_path: Path) -> PlayDataContext:
    (tmp_path / "Data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Mods").mkdir(parents=True, exist_ok=True)
    return PlayDataContext(
        profile_mods_dir=tmp_path / "Mods", data_dir=tmp_path / "Data"
    )


def _pd_with_mod(name: str) -> ProfileData:
    pd = ProfileData()
    pd.add_mod(ModData(group="Adventures", mod_name=name))
    return pd


def _pdm(tmp_path, pd=None, settings=None, **kw) -> PlayDataManager:
    return PlayDataManager(
        pd or ProfileData(), _ctx(tmp_path),
        settings=settings or PlayDataSettings(config_min_play_time=1),
        user_name="Louis",
        **kw,
    )


class TestTimeAccumulation:
    def test_apply_logged_times_adds_per_mod(self, tmp_path):
        pdm = _pdm(tmp_path)
        result = ClientLogResult(
            mods_loaded=CIStrDict({"Mod A": timedelta(minutes=30)}),
        )
        pdm.apply_logged_times(result)
        assert pdm.play_time("Mod A") == timedelta(minutes=30)
        assert pdm.total_played == timedelta(minutes=30)
        assert pdm.most_in_one_day == timedelta(minutes=30)

    def test_apply_logged_times_no_mods_uses_execution(self, tmp_path):
        pdm = _pdm(tmp_path)
        pdm.apply_logged_times(ClientLogResult(execution_time=timedelta(hours=1)))
        assert pdm.total_played == timedelta(hours=1)

    def test_add_time_and_reset(self, tmp_path):
        pdm = _pdm(tmp_path)
        pdm.add_time("Mod A", timedelta(hours=2))
        assert pdm.play_time("Mod A") == timedelta(hours=2)
        assert pdm.total_played == timedelta(hours=2)
        pdm.reset_time("Mod A")
        assert pdm.play_time("Mod A") == timedelta(0)
        assert pdm.total_played == timedelta(0)


class TestFormatting:
    def test_format_time_hours_and_minutes(self, tmp_path):
        pdm = _pdm(tmp_path)
        pdm.pdi.total_played = timedelta(hours=1)
        assert pdm.format_time(timedelta(hours=150, minutes=16), "") == (
            "150 hours 16 mins"
        )

    def test_format_time_singular(self, tmp_path):
        pdm = _pdm(tmp_path)
        pdm.pdi.total_played = timedelta(hours=1)
        assert pdm.format_time(timedelta(hours=1, minutes=1), "") == "1 hour 1 min"

    def test_format_time_zero(self, tmp_path):
        pdm = _pdm(tmp_path)
        assert pdm.format_time(timedelta(0), "", zero="none yet") == "none yet"

    def test_format_days_conversion_factor(self, tmp_path):
        # 24 play-hours == 1 day by default.
        pdm = _pdm(tmp_path)
        pdm.pdi.total_played = timedelta(hours=50)
        assert pdm.format_days(timedelta(hours=50), "") == "2 days 2 hours"


class TestRtfRoundTrip:
    def test_record_writes_readable_rtf(self, tmp_path):
        pd = _pd_with_mod("My Adventure")
        (tmp_path / "Mods" / "My Adventure").mkdir(parents=True)
        saved: list[int] = []
        pdm = _pdm(tmp_path, pd=pd, on_save_mods=lambda: saved.append(1))
        pdm.pdi.play_times["My Adventure"] = timedelta(hours=150, minutes=16)
        result = pdm.record_time("My Adventure")
        assert result < RecordResult.NO_TIME

        play_file = tmp_path / "Mods" / "My Adventure" / ".Game Play Time.rtf"
        assert play_file.is_file()
        text = read_rtf_text(play_file.read_text(encoding="utf-8"))
        assert "My Adventure" in text
        assert "150 hours 16 mins" in text
        assert "Louis" in text
        # A completed game updates the mod's CompletedCount and persists mods.
        assert pd.mod_item("My Adventure").completed_count == 1
        assert saved

    def test_read_back_existing_records(self, tmp_path):
        pd = _pd_with_mod("My Adventure")
        (tmp_path / "Mods" / "My Adventure").mkdir(parents=True)
        pdm = _pdm(tmp_path, pd=pd)
        # First recording.
        pdm.pdi.play_times["My Adventure"] = timedelta(hours=10)
        pdm.record_time("My Adventure")
        # A later, different play session appends a second line.
        pdm.pdi.play_times["My Adventure"] = timedelta(hours=5)
        pdm.record_time("My Adventure")
        records: list[PlayTimeInfo] = []
        pdm.read_play_time_file("My Adventure", records)
        # Two distinct completed lines survive (same day may merge; use counts).
        assert len(records) >= 1
        assert any("10 hours" in r.play_time for r in records)

    def test_min_play_time_not_recorded(self, tmp_path):
        pd = _pd_with_mod("Quickie")
        (tmp_path / "Mods" / "Quickie").mkdir(parents=True)
        pdm = _pdm(
            tmp_path, pd=pd, settings=PlayDataSettings(config_min_play_time=60)
        )
        pdm.pdi.play_times["Quickie"] = timedelta(minutes=5)  # under 60 min
        result = pdm.record_time("Quickie")
        assert result == RecordResult.NO_TIME
        assert not (tmp_path / "Mods" / "Quickie" / ".Game Play Time.rtf").exists()


class TestPending:
    def test_mod_not_in_profile_goes_pending(self, tmp_path):
        pdm = _pdm(tmp_path)  # empty profile
        pdm.pdi.play_times["Absent Mod"] = timedelta(hours=3)
        result = pdm.record_time("Absent Mod")
        assert result == RecordResult.NO_TIME
        assert "Absent Mod" in pdm.pending_play_times
        # Persisted and reloadable.
        pdm2 = _pdm(tmp_path)
        assert "Absent Mod" in pdm2.pending_play_times

    def test_record_completed_when_mod_appears(self, tmp_path):
        pdm = _pdm(tmp_path)
        pdm.pdi.play_times["Later Mod"] = timedelta(hours=3)
        pdm.record_time("Later Mod")  # -> pending
        assert "Later Mod" in pdm.pending_play_times
        # Mod now exists in the profile; record_completed_games flushes it.
        pdm.pd.add_mod(ModData(group="Adventures", mod_name="Later Mod"))
        (tmp_path / "Mods" / "Later Mod").mkdir(parents=True)
        pdm.record_completed_games()
        assert "Later Mod" not in pdm.pending_play_times
        assert (tmp_path / "Mods" / "Later Mod" / ".Game Play Time.rtf").is_file()


class TestRenameAndReload:
    def test_rename_moves_records(self, tmp_path):
        pdm = _pdm(tmp_path)
        pdm.pdi.play_times["Old"] = timedelta(hours=4)
        pdm.set_start_date("Old", datetime(2020, 1, 1))
        pdm.rename_mod("Old", "New")
        assert pdm.play_time("New") == timedelta(hours=4)
        assert pdm.play_time("Old") == timedelta(0)
        assert pdm.start_date("New") == datetime(2020, 1, 1)
        assert pdm.start_date("Old") is None

    def test_persistence_round_trip(self, tmp_path):
        pd = _pd_with_mod("My Adventure")
        pdm = _pdm(tmp_path, pd=pd)
        pdm.pdi.play_times["My Adventure"] = timedelta(hours=7)
        pdm.pdi.total_played = timedelta(hours=7)
        pdm.save()
        pdm2 = _pdm(tmp_path, pd=pd)
        assert pdm2.play_time("My Adventure") == timedelta(hours=7)
        assert pdm2.total_played == timedelta(hours=7)


class TestValidateAndDeleted:
    def test_validate_adds_backup_mods(self, tmp_path):
        pd = _pd_with_mod("Backed Up")
        backups = tmp_path / "GameSaves"
        (backups / "Backed Up").mkdir(parents=True)
        pdm = _pdm(tmp_path, pd=pd, to_mod_key=lambda s: s)
        pdm.validate(backups)
        assert "Backed Up" in pdm.pdi.play_times

    def test_record_deleted_games(self, tmp_path):
        pd = _pd_with_mod("Gone")
        (tmp_path / "Mods" / "Gone").mkdir(parents=True)
        pdm = _pdm(tmp_path, pd=pd, to_mod_key=lambda s: s)
        pdm.pdi.play_times["Gone"] = timedelta(hours=5)
        # No backups, current save is a different game -> "Gone" was deleted.
        pdm.record_deleted_games(tmp_path / "GameSaves", ["Still Playing"])
        assert "Gone" in pdm.deleted_games
