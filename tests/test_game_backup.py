"""Tests for game-save deactivate/activate/delete (VB GameManager backup flows)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game import game_backup as gb
from vaultkeeper.game.game_saves import GameSaveFolderType, GameSaves


def _make_save(saves_dir: Path, number: int, game: str) -> None:
    """Create a numbered NWN save folder for game ``game``.

    A SAVES-type folder's game name comes from the ``.sav`` file inside it
    (``GameSaveInfo``), so drop one named after the game.
    """
    folder = saves_dir / f"{number:06d} - {game}"
    folder.mkdir(parents=True)
    (folder / f"{game}.sav").write_bytes(b"x" * 32)


def _saves(saves_dir: Path) -> GameSaves:
    return GameSaves(GameSaveFolderType.SAVES, saves_dir)


def test_deactivate_moves_saves_to_backup(tmp_path):
    saves_dir = tmp_path / "saves"
    _make_save(saves_dir, 1, "Adventure")
    _make_save(saves_dir, 2, "Adventure")
    backup_root = tmp_path / "Backups"

    saves = _saves(saves_dir)
    game = saves.current_game_save
    result = gb.deactivate_game(saves, saves_dir, backup_root)
    assert result.ok
    assert result.moved == 2
    # Live saves dir is now empty; backup holds both folders.
    assert not any(saves_dir.iterdir())
    backup = backup_root / game
    assert backup.is_dir()
    assert len(list(backup.iterdir())) == 2


def test_deactivate_no_active_game(tmp_path):
    saves_dir = tmp_path / "saves"
    saves_dir.mkdir()
    result = gb.deactivate_game(_saves(saves_dir), saves_dir, tmp_path / "Backups")
    assert not result.ok


def test_scan_deactivated_games(tmp_path):
    backup_root = tmp_path / "Backups"
    _make_save(backup_root / "Game A", 1, "Game A")
    _make_save(backup_root / "Game B", 1, "Game B")
    _make_save(backup_root / "Game B", 2, "Game B")

    games = {g.name: g for g in gb.scan_deactivated_games(backup_root)}
    assert set(games) == {"Game A", "Game B"}
    assert games["Game B"].count == 2
    assert games["Game A"].total_size > 0


def test_activate_restores_and_removes_backup(tmp_path):
    saves_dir = tmp_path / "saves"
    saves_dir.mkdir()
    backup_root = tmp_path / "Backups"
    _make_save(backup_root / "Old Game", 1, "Old Game")
    _make_save(backup_root / "Old Game", 2, "Old Game")

    result = gb.activate_game(backup_root / "Old Game", saves_dir)
    assert result.ok
    assert result.moved == 2
    assert len(list(saves_dir.iterdir())) == 2
    # The emptied backup folder is removed.
    assert not (backup_root / "Old Game").exists()


def test_activate_deactivates_current_first(tmp_path):
    saves_dir = tmp_path / "saves"
    _make_save(saves_dir, 1, "Current Game")  # an active game is present
    backup_root = tmp_path / "Backups"
    _make_save(backup_root / "Old Game", 1, "Old Game")

    current = _saves(saves_dir)
    result = gb.activate_game(
        backup_root / "Old Game",
        saves_dir,
        current_saves=current,
        backup_root=backup_root,
    )
    assert result.ok
    # The old game is now live.
    assert any("Old Game" in p.name for p in saves_dir.iterdir())
    # The previously-active game was backed up.
    assert (backup_root / "Current Game").is_dir()


def test_delete_game_backup(tmp_path):
    backup_root = tmp_path / "Backups"
    _make_save(backup_root / "Doomed", 1, "Doomed")
    result = gb.delete_game_backup(backup_root / "Doomed")
    assert result.ok
    assert not (backup_root / "Doomed").exists()


def test_delete_missing_backup(tmp_path):
    result = gb.delete_game_backup(tmp_path / "Nope")
    assert not result.ok
