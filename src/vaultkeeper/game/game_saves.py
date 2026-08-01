"""Game-save scanning — faithful port of ``GameSaves.vb`` / ``GameSaveInfo.vb``.

Scans an NWN game-save directory (or a backup/archive tree) into a list of
:class:`GameSaveInfo` records: the number prefix, save type (quick/auto/standard),
the ``.sav`` name, the in-module location (from ``savenfo.txt``) and byte size.

The VB original runs the scan and the size sweep on ``BackgroundWorker`` threads
and raises notification events consumed by the title bar. This port is synchronous
(the work is pure I/O and we run headless); a caller that wants progress can pass a
``notify`` callback, and the UI layer can drive :meth:`GameSaves.refresh` off-thread.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path

# Reading a save folder belongs to the save package; the mod manager needs the
# same answer for its save list, and imports it from there rather than the two
# growing separate readers of the same file.
from nwnsaveeditor.save_game import (  # noqa: F401 - re-exported for callers
    GAME_LOCATION_FAILED,
    SAVE_INFO_FILE,
    _read_text_lenient,
    get_location_in_game_save,
)

#: Game name to use when there are no saves (``GameSaves.NoSavesText``).
NO_SAVES_TEXT = "No games have been saved"
#: File inside a save folder holding the in-module location (``GameSaveInfo.SaveInfo``).
#: Returned when the location can't be read (``Defs.GameLocationFailed``).


class GameSaveFolderType(IntEnum):
    """The kind of folder that contains NWN game-save directories."""

    NONE = 0
    SAVES = 1
    BACKUP = 2
    ARCHIVE = 3


class GameSaveType(IntEnum):
    """The kind of an individual save (value mirrors the NWN folder number)."""

    NONE = -1
    QUICK = 0
    AUTO = 1
    STANDARD = 2


def _dir_size(path: Path) -> int:
    """Total byte size of all files under ``path`` (FS.GetDirSize)."""
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


@dataclass
class GameSaveInfo:
    """Information about a single NWN save folder (``GameSaveInfo``)."""

    folder_type: GameSaveFolderType = GameSaveFolderType.NONE
    full_name: Path = field(default_factory=Path)
    number: int = -1
    saved: datetime = datetime.min
    byte_size: int = -1
    name: str = ""
    game_save_name: str = ""
    location: str = ""
    save_type: GameSaveType = GameSaveType.NONE
    error_messages: list[str] = field(default_factory=list)

    @classmethod
    def from_folder(
        cls, folder_type: GameSaveFolderType, info: Path
    ) -> GameSaveInfo:
        """Build a record from a save folder (VB ``New(type, DirectoryInfo)``)."""
        gsi = cls(
            folder_type=folder_type,
            full_name=info,
            name=info.name,
            byte_size=-1,
            location="",
        )
        try:
            gsi.saved = datetime.fromtimestamp(info.stat().st_mtime)
        except OSError:
            gsi.saved = datetime.min

        # Determine the type of save from the leading 6-digit number.
        if len(info.name) > 5 and info.name[:6].isdigit():
            gsi.number = int(info.name[:6])
        else:
            # User pointed at a folder that doesn't end in a numbered Saves subdir.
            gsi.number = int(GameSaveFolderType.SAVES)

        if gsi.number > GameSaveType.AUTO:
            gsi.save_type = GameSaveType.STANDARD
        else:
            gsi.save_type = GameSaveType(gsi.number)

        if folder_type == GameSaveFolderType.BACKUP:
            gsi.game_save_name = info.parent.name
        elif folder_type == GameSaveFolderType.ARCHIVE:
            gsi.game_save_name = info.parent.parent.name
        elif folder_type == GameSaveFolderType.SAVES:
            gsi.game_save_name = NO_SAVES_TEXT
            for save_file in sorted(info.glob("*.sav")):
                gsi.game_save_name = save_file.stem
                with contextlib.suppress(OSError):
                    gsi.saved = datetime.fromtimestamp(save_file.stat().st_mtime)
                # Rename any save file that has a leading space.
                if save_file.name.startswith(" "):
                    try:
                        renamed = save_file.with_name(save_file.name.lstrip())
                        save_file.rename(renamed)
                        gsi.game_save_name = gsi.game_save_name.lstrip()
                    except OSError as ex:
                        gsi.error_messages.append(
                            f"Unable to remove leading space from save file "
                            f"({save_file.name})... {ex}"
                        )
                break
            gsi.set_location()

        return gsi

    def set_location(self) -> bool:
        """Populate :attr:`location` from ``savenfo.txt`` (``SetLocation``)."""
        self.location, error = get_location_in_game_save(self.full_name)
        if error is None:
            return True
        self.error_messages.append(
            f"Unable to read the Location information from {self.name}\n{error}"
        )
        return False

    def clone(self) -> GameSaveInfo:
        return GameSaveInfo(
            folder_type=self.folder_type,
            full_name=self.full_name,
            number=self.number,
            saved=self.saved,
            byte_size=self.byte_size,
            name=self.name,
            game_save_name=self.game_save_name,
            location=self.location,
            save_type=self.save_type,
        )


class GameSaves:
    """Scanned contents of a game-save directory (``GameSaves``).

    Construct with a folder type and path and call :meth:`refresh` to populate
    :attr:`folders`. Sizes are computed as part of the refresh.
    """

    def __init__(
        self,
        folder_type: GameSaveFolderType = GameSaveFolderType.NONE,
        save_path: Path | None = None,
        *,
        notify: Callable[[], None] | None = None,
    ) -> None:
        self.folder_type = folder_type
        self.save_path = save_path
        self._notify = notify
        self.folders: list[GameSaveInfo] = []
        self.total_size: int = 0
        self.current_count: int = -1
        self.current_size: int = -1
        if save_path is not None:
            self.refresh()

    # -- Scan -------------------------------------------------------------- #
    def refresh(self) -> None:
        """Rebuild the folder list and recompute counts and sizes."""
        self.current_count = -1
        self.current_size = -1
        self.folders = []
        if self.save_path is None or not self.save_path.is_dir():
            return

        for folder in sorted(
            p for p in self.save_path.iterdir() if p.is_dir()
        ):
            self.folders.append(
                GameSaveInfo.from_folder(self.folder_type, folder)
            )
        self.folders.sort(key=lambda gsi: gsi.number)

        if self.folder_type == GameSaveFolderType.SAVES:
            info = self.current_info
            if info is None:
                self.current_count = 0
            else:
                self.current_count = sum(
                    1
                    for gsi in self.folders
                    if gsi.game_save_name == info.game_save_name
                    and gsi.save_type == GameSaveType.STANDARD
                )

        self._compute_sizes()
        if self._notify is not None:
            self._notify()

    def _compute_sizes(self) -> None:
        for info in self.folders:
            info.byte_size = _dir_size(info.full_name)
        self.total_size = sum(gsi.byte_size for gsi in self.folders)

        if self.folder_type != GameSaveFolderType.SAVES:
            return
        current = self.current_info
        if current is None:
            self.current_size = 0
        else:
            self.current_size = sum(
                gsi.byte_size
                for gsi in self.folders
                if gsi.game_save_name == current.game_save_name
            )

    # -- Derived views ----------------------------------------------------- #
    @property
    def count(self) -> int:
        return len(self.folders)

    @property
    def current_info(self) -> GameSaveInfo | None:
        """The latest save (``CurrentInfo``)."""
        if not self.folders:
            return None
        if len(self.folders) == 1:
            return self.folders[0]
        if self.folder_type != GameSaveFolderType.SAVES:
            return self.folders[-1]
        latest = self.folders[-1]
        for info in self.folders:
            if info.saved > latest.saved:
                latest = info
        return latest

    @property
    def current_game_save(self) -> str:
        """The ``.sav`` name of the current game (``CurrentGameSave``)."""
        if self.folder_type != GameSaveFolderType.SAVES:
            return self.folders[0].game_save_name if self.folders else NO_SAVES_TEXT
        info = self.current_info
        return info.game_save_name if info is not None else NO_SAVES_TEXT

    @property
    def current_location(self) -> str:
        info = self.current_info
        return info.location if info is not None else ""

    # -- Mutation ---------------------------------------------------------- #
    def remove(
        self, save_folders: list[Path]
    ) -> dict[str, list[GameSaveInfo]]:
        """Remove the given save folders, returning cloned removals by save name.

        Mirrors ``GameSaves.Remove``: size/count fields are adjusted and the removed
        items are returned grouped by ``game_save_name``. The settings side-effects
        (clearing the current PlayTimeMod) are the caller's responsibility.
        """
        wanted = {p.resolve() for p in save_folders}
        removed: dict[str, list[GameSaveInfo]] = {}
        current = self.current_game_save
        for gsi in [g for g in self.folders if g.full_name.resolve() in wanted]:
            self.total_size -= gsi.byte_size
            if (
                self.folder_type == GameSaveFolderType.SAVES
                and gsi.game_save_name == current
            ):
                self.current_size -= gsi.byte_size
                self.current_count -= 1
            removed.setdefault(gsi.game_save_name, []).append(gsi.clone())
            self.folders.remove(gsi)
        if self._notify is not None:
            self._notify()
        return removed

    def add_info(self, items: list[GameSaveInfo]) -> None:
        """Add save records, updating counts and sizes (``AddInfo``)."""
        current = self.current_game_save
        for gsi in items:
            self.folders.append(gsi)
            self.total_size += gsi.byte_size
            if (
                self.folder_type == GameSaveFolderType.SAVES
                and gsi.game_save_name == current
            ):
                self.current_size += gsi.byte_size
                self.current_count += 1
                if gsi.location == "":
                    gsi.set_location()
        self.folders.sort(key=lambda gsi: gsi.number)
        if self._notify is not None:
            self._notify()
