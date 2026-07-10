"""Game-save backup / activate — port of ``GameManager.MenuActions.vb`` (backup flows).

The Game Saves Manager can **deactivate** the current game (move its save folders out
of NWN's live ``saves`` directory into a per-game backup under
``Backups/Data Backups/Game Saves/<game>/``), **activate** a previously-deactivated
game (move a backup's saves back into the live directory, deactivating the current one
first), and **delete** a deactivated game's backup. This is the headless core of VB
``DeactivateGame`` / ``ActivateGame`` / ``DeleteGame``; the archive/reduce/restore
slice lives in :mod:`vaultkeeper.game.save_archive`.

Sizes/counts come from the :class:`GameSaves` scanner. All folder moves go through
:mod:`vaultkeeper.core.fs` (``move_dir``), matching the archive code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vaultkeeper.core import fs
from vaultkeeper.core.formatting import to_plural
from vaultkeeper.game.game_saves import (
    NO_SAVES_TEXT,
    GameSaveFolderType,
    GameSaves,
)

#: Sub-path (under the store root) holding deactivated-game backups (VB
#: ``Paths.GameSaves`` — kept consistent with the archived-saves path convention).
GAME_SAVES_SUBPATH = ("Backups", "Data Backups", "Game Saves")


@dataclass
class BackupResult:
    """Outcome of a deactivate / activate / delete operation."""

    ok: bool
    moved: int = 0
    errors: int = 0
    folder: Path | None = None
    message: str = ""


@dataclass
class DeactivatedGame:
    """A previously-deactivated game held in the backup area (VB backup ``SaveList`` row)."""

    name: str
    folder: Path
    saves: GameSaves = field(default_factory=GameSaves)

    @property
    def count(self) -> int:
        return self.saves.count

    @property
    def total_size(self) -> int:
        return self.saves.total_size


def deactivate_game(saves: GameSaves, saves_dir: Path, backup_root: Path) -> BackupResult:
    """Move the current game's live saves into a backup folder (VB ``DeactivateGame``).

    Creates ``backup_root/<current game>/`` and moves every folder in ``saves`` into
    it (VB moves ``NwGs.Folders``), updating ``saves`` in place. Returns the moved
    count and the backup folder.
    """
    game_name = saves.current_game_save
    if not saves.folders or game_name == NO_SAVES_TEXT:
        return BackupResult(ok=False, message="There is no active game to deactivate.")

    backup_folder = backup_root / game_name
    try:
        fs.ensure_dir(backup_folder)
    except OSError:
        return BackupResult(ok=False, message="Unable to create the backup folder.")

    moved_paths: list[Path] = []
    errors = 0
    for gsi in list(saves.folders):
        target = backup_folder / gsi.name
        try:
            fs.move_dir(gsi.full_name, target, overwrite=True)
            moved_paths.append(gsi.full_name)
        except OSError:
            errors += 1
    if moved_paths:
        saves.remove(moved_paths)

    message = f"Deactivated {game_name}: moved {to_plural(len(moved_paths), 'game save')}."
    if errors:
        message += f" Errors: {errors:,}."
    return BackupResult(
        ok=bool(moved_paths),
        moved=len(moved_paths),
        errors=errors,
        folder=backup_folder,
        message=message,
    )


def scan_deactivated_games(backup_root: Path) -> list[DeactivatedGame]:
    """Enumerate the deactivated games held in the backup area (VB backup ``SaveList``)."""
    if not backup_root.is_dir():
        return []
    games: list[DeactivatedGame] = []
    for folder in sorted(p for p in backup_root.iterdir() if p.is_dir()):
        saves = GameSaves(GameSaveFolderType.BACKUP, folder)
        games.append(DeactivatedGame(name=folder.name, folder=folder, saves=saves))
    return games


def activate_game(
    backup_folder: Path,
    saves_dir: Path,
    *,
    current_saves: GameSaves | None = None,
    backup_root: Path | None = None,
) -> BackupResult:
    """Restore a deactivated game to the live saves directory (VB ``ActivateGame``).

    If ``current_saves`` has active folders they are deactivated first (moved to
    ``backup_root``). Then every save folder in ``backup_folder`` is moved into
    ``saves_dir`` and the (now empty) backup folder is removed.
    """
    if not backup_folder.is_dir():
        return BackupResult(ok=False, message="The backup folder no longer exists.")

    # Backup the currently-active game first (VB: DeactivateGame when SaveCount > 0).
    if (
        current_saves is not None
        and current_saves.folders
        and backup_root is not None
    ):
        deactivate_game(current_saves, saves_dir, backup_root)

    fs.ensure_dir(saves_dir)
    moved = 0
    errors = 0
    for folder in sorted(p for p in backup_folder.iterdir() if p.is_dir()):
        target = saves_dir / folder.name
        try:
            fs.move_dir(folder, target, overwrite=True)
            moved += 1
        except OSError:
            errors += 1

    if moved and not errors and not any(backup_folder.iterdir()):
        fs.delete(backup_folder, to_trash=False)

    game_name = backup_folder.name
    message = f"Activated {game_name}: restored {to_plural(moved, 'game save')}."
    if errors:
        message += f" Errors: {errors:,}."
    return BackupResult(
        ok=bool(moved),
        moved=moved,
        errors=errors,
        folder=saves_dir,
        message=message,
    )


def delete_game_backup(backup_folder: Path, *, to_trash: bool = False) -> BackupResult:
    """Delete a deactivated game's backup folder (VB ``DeleteGame`` for a backup)."""
    if not backup_folder.is_dir():
        return BackupResult(ok=False, message="The backup folder no longer exists.")
    name = backup_folder.name
    try:
        fs.delete(backup_folder, to_trash=to_trash)
    except OSError:
        return BackupResult(ok=False, folder=backup_folder, message=f"Unable to delete {name}.")
    return BackupResult(ok=True, folder=backup_folder, message=f"Deleted backup for {name}.")
