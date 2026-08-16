"""Archive / reduce / restore of NWN game saves (VB ``GameManager`` actions).

The Game Saves Manager can *reduce* the number of active game saves by archiving the
oldest ones, and later *restore* an archived set. This module is the headless core:

* :func:`archive_game_saves` — port of ``GameManager.ArchiveGames`` (the *Reduce*
  action): keep the newest ``keep`` saves (plus the leading quick/auto saves) active
  and move the oldest ones into ``Archived Saves/<game>/<range>/``, where ``<range>``
  is ``<firstNumber:000000>-<lastNumber:000000>``.
* :func:`scan_archived_ranges` — enumerate a game's archived ranges (VB
  ``ArchivedFolder``) as :class:`~vaultkeeper.game.game_saves.GameSaves` instances.
* :func:`restore_game_saves` — port of ``GameManager.RestoreGames`` / ``Restore``:
  move an archived range's save folders back to the live saves directory (never
  overwriting a live save), then delete the emptied range (and game) folder.

Bounded: the VB deactivate/activate/delete-game *backup* flows, the running
``ArchiveFolderSize`` accounting and the stateful GameManager form (ActiveGame,
restart-to-rebuild) are not ported — this is the archive/reduce/restore slice only.
The oldest/newest ordering, the leading quick/auto guard and the range-folder naming
are faithful to ``GameManager.MenuActions.vb`` (ArchiveGames @26, RestoreGames @180,
Restore @313).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vaultkeeper.core import fs
from vaultkeeper.core.formatting import to_plural
from vaultkeeper.game.game_saves import (
    NO_SAVES_TEXT,
    GameSaveFolderType,
    GameSaves,
    GameSaveType,
)

#: Sub-path (under the store's ``Backups`` folder) that holds archived game saves
#: (VB ``Paths`` — ``Backups\Data Backups\Archived Saves``).
ARCHIVED_SAVES_SUBPATH = ("Backups", "Data Backups", "Archived Saves")


@dataclass
class ReduceResult:
    """Outcome of a Reduce (archive-oldest) action."""

    ok: bool
    moved: int = 0
    errors: int = 0
    range_name: str = ""
    range_folder: Path | None = None
    message: str = ""


@dataclass
class RestoreResult:
    """Outcome of restoring an archived range."""

    ok: bool
    restored: int = 0
    errors: int = 0
    message: str = ""


@dataclass
class ArchivedRange:
    """One archived set of game saves (VB ``ArchivedFolder`` entry)."""

    name: str
    folder: Path
    saves: GameSaves


def reduce_indices(folders: list, keep: int) -> tuple[int, int] | None:
    """The ``[start, end]`` folder indices to archive (VB ``ArchiveGames`` @38-49).

    Keeps the newest ``keep`` saves active and skips the leading up-to-two quick/auto
    saves (they stay active). Returns ``None`` if there is nothing to archive.
    """
    count = len(folders)
    if count == 0:
        return None
    end_index = (count - 1) - keep
    start_index = 0
    for i in range(min(2, count)):
        if folders[i].save_type in (GameSaveType.QUICK, GameSaveType.AUTO):
            start_index += 1
    if end_index > count - 1:
        end_index = count - 1
    if end_index < start_index:
        return None
    return start_index, end_index


def archive_game_saves(
    saves: GameSaves,
    archived_root: Path,
    *,
    keep: int,
    on_existing: str = "overwrite",
) -> ReduceResult:
    """Archive the oldest active saves (VB ``GameManager.ArchiveGames``).

    ``saves`` is the live game-saves scan (``GameSaveFolderType.SAVES``). Moves the
    oldest folders (see :func:`reduce_indices`) into
    ``archived_root/<game>/<range>/`` and updates ``saves`` in place (removing the
    moved folders). ``keep`` is the number of newest saves to leave active.

    ``on_existing`` handles a range folder that was already archived (VB's three-way
    prompt): ``"overwrite"`` merges into it, ``"replace"`` recycles it first,
    ``"cancel"`` aborts.
    """
    game_name = saves.current_game_save
    if not saves.folders or game_name == NO_SAVES_TEXT:
        return ReduceResult(ok=False, message="There are no game saves to reduce.")

    indices = reduce_indices(saves.folders, keep)
    if indices is None:
        return ReduceResult(
            ok=False, message="There are not enough game saves to reduce."
        )
    start, end = indices

    game_archive = archived_root / game_name
    range_name = (
        f"{saves.folders[start].number:06d}-{saves.folders[end].number:06d}"
    )
    range_folder = game_archive / range_name

    if range_folder.is_dir() and any(p.is_dir() for p in range_folder.iterdir()):
        if on_existing == "cancel":
            return ReduceResult(
                ok=False,
                range_name=range_name,
                range_folder=range_folder,
                message="These game saves have already been archived.",
            )
        if on_existing == "replace":
            fs.delete(range_folder, to_trash=True)
    fs.ensure_dir(range_folder)

    moved_paths: list[Path] = []
    errors = 0
    for index in range(start, end + 1):
        gsi = saves.folders[index]
        target = range_folder / gsi.name
        try:
            fs.move_dir(gsi.full_name, target, overwrite=True)
            moved_paths.append(gsi.full_name)
        except OSError:
            errors += 1

    if moved_paths:
        saves.remove(moved_paths)

    message = (
        f"Moved {to_plural(len(moved_paths), 'game save')} "
        f"to {game_name} archives folder."
    )
    if errors:
        message += f" Errors: {errors:,}."
    return ReduceResult(
        ok=bool(moved_paths),
        moved=len(moved_paths),
        errors=errors,
        range_name=range_name,
        range_folder=range_folder,
        message=message,
    )


def archive_finished_saves(
    saves: GameSaves, archived_root: Path, game_name: str
) -> ReduceResult:
    """Move *every* live save for ``game_name`` into the archive — the safe form of
    VB ``Finished``.

    ``Finished`` records a mod's completion by clearing its game saves. Deleting
    them outright means a mis-click destroys a whole game's saves at once —
    permanently, with the Recycle-Bin-for-game-saves preference off. Archiving them
    instead still clears the active list (which is what records the completion) but
    leaves every save restorable from the Game Saves Manager. Same
    ``<game>/<first>-<last>/`` layout as :func:`archive_game_saves`, so the existing
    restore path covers it unchanged.
    """
    wanted = [gsi for gsi in saves.folders if gsi.game_save_name == game_name]
    if not wanted:
        return ReduceResult(ok=False, message=f"No live saves for '{game_name}'.")

    numbers = [gsi.number for gsi in wanted]
    range_name = f"{min(numbers):06d}-{max(numbers):06d}"
    range_folder = archived_root / game_name / range_name
    fs.ensure_dir(range_folder)

    moved_paths: list[Path] = []
    errors = 0
    for gsi in wanted:
        try:
            fs.move_dir(gsi.full_name, range_folder / gsi.name, overwrite=True)
            moved_paths.append(gsi.full_name)
        except OSError:
            errors += 1

    if moved_paths:
        saves.remove(moved_paths)

    message = f"Archived {to_plural(len(moved_paths), 'game save')} for {game_name}."
    if errors:
        message += f" Errors: {errors:,}."
    return ReduceResult(
        ok=bool(moved_paths),
        moved=len(moved_paths),
        errors=errors,
        range_name=range_name,
        range_folder=range_folder,
        message=message,
    )


def scan_archived_ranges(archived_root: Path, game_name: str) -> list[ArchivedRange]:
    """Enumerate a game's archived ranges (VB ``ArchivedFolder``)."""
    game_archive = archived_root / game_name
    if not game_archive.is_dir():
        return []
    ranges: list[ArchivedRange] = []
    for range_dir in sorted(p for p in game_archive.iterdir() if p.is_dir()):
        ranges.append(
            ArchivedRange(
                name=range_dir.name,
                folder=range_dir,
                saves=GameSaves(GameSaveFolderType.ARCHIVE, range_dir),
            )
        )
    return ranges


def restore_game_saves(range_folder: Path, saves_dir: Path) -> RestoreResult:
    """Restore an archived range's saves to the live folder (VB ``RestoreGames``).

    Moves each save folder in ``range_folder`` back to ``saves_dir`` without
    overwriting a live save (VB ``IOAction.Fail``). When every folder moves cleanly
    the emptied range folder is deleted, and the game folder too if it is now empty.
    """
    if not range_folder.is_dir():
        return RestoreResult(ok=False, message="Archived game saves not found.")

    fs.ensure_dir(saves_dir)
    restored = 0
    errors = 0
    for child in sorted(p for p in range_folder.iterdir() if p.is_dir()):
        try:
            fs.move_dir(child, saves_dir / child.name, overwrite=False)
            restored += 1
        except OSError:
            errors += 1

    if errors == 0:
        fs.delete(range_folder)
        game_folder = range_folder.parent
        if game_folder.is_dir() and not any(game_folder.iterdir()):
            fs.delete(game_folder)

    message = f"Restored {to_plural(restored, 'game save')}."
    if errors:
        message += f" Errors: {errors:,}."
    return RestoreResult(
        ok=errors == 0 and restored > 0,
        restored=restored,
        errors=errors,
        message=message,
    )


def delete_archived_range(range_folder: Path, *, to_trash: bool = True) -> RestoreResult:
    """Delete an archived range (``deletearchives.htm``).

    "The selected range is moved to the Recycle Bin or permanently deleted
    depending on your Recycle Bin for Game Saves Preference" — which is the
    whole of ``restoringdeletedsavesfromtherecy.htm``: a range that went to the
    recycle bin can be put back, one that did not is gone. So the preference is
    the argument, and it defaults to the recoverable answer.

    The saves are counted before the delete; afterwards there is nothing left to
    count, and "deleted 0 game saves" is not what happened.
    """
    if not range_folder.is_dir():
        return RestoreResult(ok=False, message="Archived game saves not found.")

    saves = sum(1 for p in range_folder.iterdir() if p.is_dir())
    name = range_folder.name
    try:
        fs.delete(range_folder, to_trash=to_trash)
    except OSError:
        return RestoreResult(ok=False, message=f"Unable to delete {name}.")

    game_folder = range_folder.parent
    if game_folder.is_dir() and not any(game_folder.iterdir()):
        fs.delete(game_folder)

    where = "to the recycle bin" if to_trash else "permanently"
    return RestoreResult(
        ok=True,
        restored=saves,
        message=f"Deleted {name} ({to_plural(saves, 'game save')}) {where}.",
    )
