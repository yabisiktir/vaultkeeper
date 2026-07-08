"""PlayLoop — the app-level composition of the Phase-5 play-tracking domain.

Ties the (headless, individually-tested) play-loop modules together the way the VB
main form does at exit-processing time: :class:`GameMapper` resolves logged/save
names to mod names, :func:`parse_client_log` attributes a session's time per mod,
:class:`PlayDataManager` records it (and the durable RTF files), and :class:`GameSaves`
scans the save folder. It is UI-free so the whole play loop is testable without Qt.

Actually launching the game (and detecting its exit) is OS-specific and lives in the
UI layer; this class handles everything that happens *around* a play session:
:meth:`process_session` (log -> per-mod times -> record) and :meth:`game_saves`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.game.client_log import parse_client_log
from vaultkeeper.game.game_mapper import GameMapper, GameMapperContext
from vaultkeeper.game.game_saves import GameSaveFolderType, GameSaves
from vaultkeeper.game.module_reader import ErfModuleReader
from vaultkeeper.game.play_data_manager import (
    PlayDataContext,
    PlayDataManager,
    PlayDataSettings,
)


class PlayLoop:
    """Composes GameMapper + PlayDataManager + GameSaves for the active profile."""

    def __init__(
        self,
        pd: ProfileData,
        *,
        profile_mods_dir: Path,
        data_dir: Path,
        saves_dir: Path,
        log_path: Path,
        is_engine_log: bool = False,
        settings: PlayDataSettings | None = None,
        on_save: Callable[[], None] = lambda: None,
        prompter=None,  # noqa: ANN001 - GameMapperPrompter (Qt or default)
        download_rules=None,  # noqa: ANN001 - vault.DownloadRules for save-name rules
    ) -> None:
        self.pd = pd
        self.saves_dir = saves_dir
        self.log_path = log_path
        self.is_engine_log = is_engine_log

        from vaultkeeper.vault.download_rules import DownloadRules

        rules = download_rules or DownloadRules()
        self.game_mapper = GameMapper(
            pd,
            GameMapperContext(
                profiles_dir=profile_mods_dir.parent,
                active_profile=profile_mods_dir.name,
                data_dir=data_dir,
            ),
            module_reader=ErfModuleReader(),
            prompter=prompter,
            save_name_rules=rules.save_name_rules,
            save_name_removed_chars=rules.save_name_removed_chars,
            auto_scan=False,
        )
        self.play_data = PlayDataManager(
            pd,
            PlayDataContext(profile_mods_dir=profile_mods_dir, data_dir=data_dir),
            settings=settings,
            to_mod_key=self.game_mapper.save_name_to_mod_name,
            on_save_mods=on_save,
        )

    # -- Game saves -------------------------------------------------------- #
    def game_saves(self) -> GameSaves:
        """Scan the NWN saves folder (VB NwGs)."""
        return GameSaves(GameSaveFolderType.SAVES, self.saves_dir)

    def current_game_summary(self) -> str:
        """A one-line summary of the current save (mod, location, count)."""
        gs = self.game_saves()
        if gs.count == 0:
            return "No games have been saved"
        save = gs.current_game_save
        # A passive summary must never block on the interactive prompter.
        mod = self.game_mapper.save_name_to_mod_name(save, interactive=False) or save
        location = gs.current_location
        parts = [f"Playing: {mod}"]
        if location:
            parts.append(f"at {location}")
        parts.append(f"({gs.current_count} save(s))")
        return "  ".join(parts)

    # -- Session processing ------------------------------------------------ #
    def _read_log_lines(self) -> list[str]:
        if not self.log_path.is_file():
            return []
        try:
            return self.log_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            return []

    def process_session(self, started: datetime, stopped: datetime) -> dict:
        """Attribute a finished play session's time to mods and record it.

        Reads the NWN client/engine log between ``started`` and ``stopped``,
        resolves module names via GameMapper, folds the per-mod durations into the
        play-time totals, and persists. Returns a small summary dict.
        """
        lines = self._read_log_lines()
        result = parse_client_log(
            lines,
            started,
            stopped,
            is_engine_log=self.is_engine_log,
            mods_started=self.play_data.mods_started,
            save_name_to_mod_name=self.game_mapper.save_name_to_mod_name,
            log_name_to_mod_name=self.game_mapper.log_name_to_mod_name,
        )
        self.play_data.apply_logged_times(result)
        self.play_data.save()
        return {
            "mods": {name: span for name, span in result.mods_loaded.items()},
            "execution_time": result.execution_time,
            "missing_hak_files": result.missing_hak_files,
            "total_played": self.play_data.total_played,
            "total_today": self.play_data.total_today,
        }

    # -- Play-time queries ------------------------------------------------- #
    def play_time(self, mod_name: str):
        return self.play_data.play_time(mod_name)

    @property
    def total_played(self):
        return self.play_data.total_played
