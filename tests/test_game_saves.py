"""Tests for the game-save scanner (GameSaves / GameSaveInfo)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from vaultkeeper.game.game_saves import (
    NO_SAVES_TEXT,
    GameSaveFolderType,
    GameSaveInfo,
    GameSaves,
    GameSaveType,
    get_location_in_game_save,
)


def _make_save(
    root: Path, folder: str, sav_stem: str, location: str = "", *, mtime: float | None = None
) -> Path:
    d = root / folder
    d.mkdir()
    (d / f"{sav_stem}.sav").write_bytes(b"\x00" * 16)
    if location:
        (d / "savenfo.txt").write_text(location, encoding="utf-8")
    if mtime is not None:
        os.utime(d / f"{sav_stem}.sav", (mtime, mtime))
    return d


class TestGetLocation:
    def test_strips_leading_dots_and_space(self, tmp_path):
        (tmp_path / "savenfo.txt").write_text("...  Aarin's Lodge", encoding="utf-8")
        loc, err = get_location_in_game_save(tmp_path)
        assert loc == "Aarin's Lodge"
        assert err is None

    def test_missing_file(self, tmp_path):
        loc, err = get_location_in_game_save(tmp_path)
        assert err is not None
        assert "does not exist" in err


class TestGameSaveInfo:
    def test_quicksave_number_and_type(self, tmp_path):
        d = _make_save(tmp_path, "000000 - quicksave", "Chapter Three", "Aarin's Lodge")
        gsi = GameSaveInfo.from_folder(GameSaveFolderType.SAVES, d)
        assert gsi.number == 0
        assert gsi.save_type == GameSaveType.QUICK
        assert gsi.game_save_name == "Chapter Three"
        assert gsi.location == "Aarin's Lodge"

    def test_autosave_type(self, tmp_path):
        d = _make_save(tmp_path, "000001 - Auto Save", "MyMod")
        gsi = GameSaveInfo.from_folder(GameSaveFolderType.SAVES, d)
        assert gsi.number == 1
        assert gsi.save_type == GameSaveType.AUTO

    def test_standard_type(self, tmp_path):
        d = _make_save(tmp_path, "000007 - gor", "MyMod")
        gsi = GameSaveInfo.from_folder(GameSaveFolderType.SAVES, d)
        assert gsi.number == 7
        assert gsi.save_type == GameSaveType.STANDARD

    def test_leading_space_sav_renamed(self, tmp_path):
        d = tmp_path / "000002 - birr"
        d.mkdir()
        (d / " Spaced.sav").write_bytes(b"\x00")
        gsi = GameSaveInfo.from_folder(GameSaveFolderType.SAVES, d)
        assert gsi.game_save_name == "Spaced"
        assert (d / "Spaced.sav").exists()
        assert not (d / " Spaced.sav").exists()

    def test_backup_uses_parent_name(self, tmp_path):
        parent = tmp_path / "MyMod"
        parent.mkdir()
        d = parent / "000003 - save"
        d.mkdir()
        gsi = GameSaveInfo.from_folder(GameSaveFolderType.BACKUP, d)
        assert gsi.game_save_name == "MyMod"


class TestGameSaves:
    def test_scan_sorts_and_sizes(self, tmp_path):
        _make_save(tmp_path, "000002 - birr", "Adventure")
        _make_save(tmp_path, "000000 - quicksave", "Adventure")
        _make_save(tmp_path, "000001 - Auto Save", "Adventure")
        gs = GameSaves(GameSaveFolderType.SAVES, tmp_path)
        assert [g.number for g in gs.folders] == [0, 1, 2]
        assert gs.count == 3
        assert gs.total_size == 3 * 16

    def test_current_info_is_latest_saved(self, tmp_path):
        _make_save(tmp_path, "000000 - quicksave", "Adventure", mtime=1000)
        _make_save(tmp_path, "000002 - birr", "Adventure", mtime=5000)
        _make_save(tmp_path, "000001 - Auto Save", "Adventure", mtime=2000)
        gs = GameSaves(GameSaveFolderType.SAVES, tmp_path)
        assert gs.current_info.number == 2
        assert gs.current_game_save == "Adventure"

    def test_current_count_excludes_quick_and_auto(self, tmp_path):
        # Standard saves for the current game are counted; quick/auto are not.
        _make_save(tmp_path, "000000 - quicksave", "Adventure")
        _make_save(tmp_path, "000001 - Auto Save", "Adventure")
        _make_save(tmp_path, "000002 - birr", "Adventure")
        _make_save(tmp_path, "000003 - ikii", "Adventure")
        gs = GameSaves(GameSaveFolderType.SAVES, tmp_path)
        assert gs.current_count == 2

    def test_empty_dir_reports_no_saves(self, tmp_path):
        gs = GameSaves(GameSaveFolderType.SAVES, tmp_path)
        assert gs.count == 0
        assert gs.current_info is None
        assert gs.current_game_save == NO_SAVES_TEXT

    def test_remove_returns_grouped_clones(self, tmp_path):
        d0 = _make_save(tmp_path, "000002 - birr", "Adventure")
        _make_save(tmp_path, "000003 - ikii", "Adventure")
        gs = GameSaves(GameSaveFolderType.SAVES, tmp_path)
        removed = gs.remove([d0])
        assert "Adventure" in removed
        assert len(removed["Adventure"]) == 1
        assert gs.count == 1

    def test_notify_called_on_refresh(self, tmp_path):
        calls: list[int] = []
        _make_save(tmp_path, "000000 - quicksave", "Adventure")
        GameSaves(GameSaveFolderType.SAVES, tmp_path, notify=lambda: calls.append(1))
        assert calls  # notify fired at least once


REAL_SAVES = Path.home() / "Documents" / "Neverwinter Nights" / "saves"


@pytest.mark.skipif(not REAL_SAVES.is_dir(), reason="No real NWN saves on this machine")
class TestRealSaves:
    def test_scan_real_saves(self):
        gs = GameSaves(GameSaveFolderType.SAVES, REAL_SAVES)
        assert gs.count > 0
        # Every scanned folder should have parsed a number and a save name.
        for info in gs.folders:
            assert info.number >= 0
            assert info.game_save_name != ""
        # The current game should resolve to a real .sav name (not the placeholder).
        assert gs.current_game_save != NO_SAVES_TEXT
