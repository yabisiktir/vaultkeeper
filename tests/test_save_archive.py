"""Tests for game-save archive/reduce/restore (VB GameManager ArchiveGames/RestoreGames)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game.game_saves import GameSaveFolderType, GameSaves
from vaultkeeper.game.save_archive import (
    archive_game_saves,
    reduce_indices,
    restore_game_saves,
    scan_archived_ranges,
)


def _make_saves(saves_dir: Path, specs: list[tuple[str, str]]) -> None:
    for folder, sav in specs:
        d = saves_dir / folder
        d.mkdir(parents=True)
        (d / f"{sav}.sav").write_bytes(b"\x00" * 16)
        (d / "savenfo.txt").write_text("Somewhere", encoding="utf-8")


_FIVE = [
    ("000000 - quick", "Adventure"),
    ("000001 - auto", "Adventure"),
    ("000002 - camp", "Adventure"),
    ("000003 - town", "Adventure"),
    ("000004 - keep", "Adventure"),
]


def test_reduce_indices_skips_leading_quick_auto_and_keeps_newest(tmp_path):
    saves_dir = tmp_path / "saves"
    _make_saves(saves_dir, _FIVE)
    gs = GameSaves(GameSaveFolderType.SAVES, saves_dir)
    # keep=1 -> archive everything except the leading quick+auto and the newest.
    assert reduce_indices(gs.folders, 1) == (2, 3)
    # keep too high -> nothing to archive.
    assert reduce_indices(gs.folders, 100) is None
    assert reduce_indices([], 1) is None


def test_archive_and_restore_round_trip(tmp_path):
    saves_dir = tmp_path / "saves"
    _make_saves(saves_dir, _FIVE)
    archived = tmp_path / "Archived Saves"
    gs = GameSaves(GameSaveFolderType.SAVES, saves_dir)

    result = archive_game_saves(gs, archived, keep=1)
    assert result.ok
    assert result.moved == 2
    assert result.errors == 0
    assert result.range_name == "000002-000003"
    assert "Moved 2 game saves" in result.message
    # Live saves reduced to the kept three (in-place update).
    assert {f.name for f in gs.folders} == {
        "000000 - quick",
        "000001 - auto",
        "000004 - keep",
    }
    range_folder = archived / "Adventure" / "000002-000003"
    assert (range_folder / "000002 - camp").is_dir()
    assert not (saves_dir / "000002 - camp").exists()

    ranges = scan_archived_ranges(archived, "Adventure")
    assert [r.name for r in ranges] == ["000002-000003"]
    assert ranges[0].saves.count == 2

    restore = restore_game_saves(range_folder, saves_dir)
    assert restore.ok
    assert restore.restored == 2
    assert "Restored 2 game saves" in restore.message
    assert (saves_dir / "000002 - camp").is_dir()
    # The emptied range and game folders are removed.
    assert not range_folder.exists()
    assert not (archived / "Adventure").exists()


def test_archive_no_saves(tmp_path):
    saves_dir = tmp_path / "saves"
    saves_dir.mkdir()
    gs = GameSaves(GameSaveFolderType.SAVES, saves_dir)
    result = archive_game_saves(gs, tmp_path / "arc", keep=1)
    assert result.ok is False
    assert "no game saves" in result.message.lower()


def test_archive_existing_range_cancel(tmp_path):
    saves_dir = tmp_path / "saves"
    _make_saves(saves_dir, _FIVE)
    archived = tmp_path / "Archived Saves"
    # Pre-seed the range folder with content so it counts as "already archived".
    seeded = archived / "Adventure" / "000002-000003" / "old"
    seeded.mkdir(parents=True)
    gs = GameSaves(GameSaveFolderType.SAVES, saves_dir)

    result = archive_game_saves(gs, archived, keep=1, on_existing="cancel")
    assert result.ok is False
    assert "already been archived" in result.message
    # Nothing moved.
    assert (saves_dir / "000002 - camp").is_dir()


def test_restore_missing_range(tmp_path):
    result = restore_game_saves(tmp_path / "nope", tmp_path / "saves")
    assert result.ok is False
    assert result.restored == 0


def test_restore_does_not_clobber_live_save(tmp_path):
    saves_dir = tmp_path / "saves"
    _make_saves(saves_dir, [("000002 - camp", "Adventure")])
    range_folder = tmp_path / "arc" / "Adventure" / "000002-000003"
    (range_folder / "000002 - camp").mkdir(parents=True)
    (range_folder / "000002 - camp" / "Adventure.sav").write_bytes(b"\x00")

    result = restore_game_saves(range_folder, saves_dir)
    assert result.errors == 1  # the live 000002 - camp already exists -> fail, not clobber
    assert result.ok is False
    # The archived copy is left in place because the restore did not fully succeed.
    assert (range_folder / "000002 - camp").is_dir()
