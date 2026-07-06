"""PlayDataManager — records and reports NWN play time.

Faithful headless port of ``PlayDataManager.vb`` (recording + RTF play-time files +
formatting). It owns the :class:`~vaultkeeper.core.play_time.PlayData` database (per-
mod durations + totals), the ``ModsStarted`` start-date map and the ``PendingPlayTimes``
map for mods not present in the current profile. The **durable source of truth** is the
per-mod ``.Game Play Time.rtf`` file in each mod folder; the dictionary is a cache that
``validate``/``rebuild`` reconcile against it.

Cross-cutting concerns are injected so the engine runs and tests headlessly:

* ``settings`` — the handful of ``My.Settings`` fields the engine reads/writes
  (:class:`PlayDataSettings`); the real app backs this with its config store.
* ``to_mod_key`` — ``GameMapper.SaveNameToModName`` (turns save/backup folder names
  into mod names); identity by default.
* ``on_save_mods`` — persist ``ModData`` after ``CompletedCount``/``DateCompleted``
  changes (``pd.SaveMods``).
* ``on_contents_refreshed`` — UI hook after a play-time file is (re)written.

Shared-store sync (``SyncPlayTimes``) and the pre-5.0 ``Migrate`` path are out of
scope here (Phase 6/legacy) and intentionally omitted.
"""

from __future__ import annotations

import getpass
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.ci_dict import CIStrDict
from vaultkeeper.core.formatting import (
    parse_date_string,
    to_date_string,
    to_plural,
)
from vaultkeeper.core.log import get_logger
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.play_time import (
    PlayData,
    PlayTimeInfo,
    sort_play_times,
)
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.rtf import read_rtf_text, write_rtf
from vaultkeeper.game.client_log import ClientLogResult
from vaultkeeper.persistence.json_store import read_json, write_json

log = get_logger(__name__)


class RecordResult(IntEnum):
    """Result of a Record operation (values < NoTime are success)."""

    NONE = 0
    CREATED = 1
    UPDATED = 2
    NO_TIME = 3
    NOT_CONNECTED = 4
    PROFILE_DOES_NOT_EXIST = 5
    READ_ERROR = 6
    WRITE_ERROR = 7


@dataclass
class PlayDataSettings:
    """The ``My.Settings`` fields PlayDataManager reads and writes."""

    play_time_mod: str = ""
    play_time: timedelta = timedelta(0)
    #: A play session shorter than this many minutes is not recorded.
    config_min_play_time: int = 1
    #: Play-time hours that count as one "day" in FormatDays.
    config_day_conversion_factor: int = 24

    def save(self) -> None:  # pragma: no cover - overridden when wired to a store
        """Persist settings (no-op default; the app injects real persistence)."""


@dataclass
class PlayDataContext:
    """Where PlayDataManager finds mod folders and stores its data files."""

    profile_mods_dir: Path
    data_dir: Path
    play_time_filename: str = C.PLAY_TIME_FILE

    def mod_path(self, mod_name: str) -> Path:
        return self.profile_mods_dir / mod_name

    def play_time_file(self, mod_name: str) -> Path:
        return self.mod_path(mod_name) / self.play_time_filename


def _current_user() -> str:
    """OS user name with the first letter upper-cased (VB Environment.UserName)."""
    try:
        user = getpass.getuser()
    except Exception:  # pragma: no cover - getuser can raise on odd environments
        user = "User"
    return f"{user[:1].upper()}{user[1:]}" if user else "User"


class PlayDataManager:
    """Records play time and maintains the per-mod RTF play-time files."""

    def __init__(
        self,
        pd: ProfileData,
        ctx: PlayDataContext,
        *,
        settings: PlayDataSettings | None = None,
        user_name: str | None = None,
        to_mod_key: Callable[[str], str] = lambda s: s,
        on_save_mods: Callable[[], None] = lambda: None,
        on_contents_refreshed: Callable[[str, Path], None] = lambda name, path: None,
    ) -> None:
        self.pd = pd
        self.ctx = ctx
        self.settings = settings or PlayDataSettings()
        self.user_name = user_name or _current_user()
        self.to_mod_key = to_mod_key
        self.on_save_mods = on_save_mods
        self.on_contents_refreshed = on_contents_refreshed

        self.pdi = PlayData()
        self.mods_started: CIStrDict[datetime] = CIStrDict()
        self.pending_play_times: CIStrDict[list[PlayTimeInfo]] = CIStrDict()
        self.recorded_games: list[str] = []
        self.deleted_games: list[str] = []
        self.filename: Path | None = None
        self.result = RecordResult.NONE

        self._load()

    # -- Data files -------------------------------------------------------- #
    @property
    def _play_data_file(self) -> Path:
        return self.ctx.data_dir / "PlayTimeData.json"

    @property
    def _mods_started_file(self) -> Path:
        return self.ctx.data_dir / "ModsStarted.json"

    @property
    def _pending_file(self) -> Path:
        return self.ctx.data_dir / "PlayTimesPending.json"

    def _load(self) -> None:
        loaded = _load_play_data(self._play_data_file)
        self.pdi.total_played = loaded.total_played
        self.pdi.last_played = loaded.last_played
        self.pdi.most_in_one_day = loaded.most_in_one_day
        if self.pdi.last_played != to_date_string(datetime.now()):
            self.pdi.total_today = timedelta(0)
        else:
            self.pdi.total_today = loaded.total_today
        self.pdi.play_times = CIStrDict(loaded.play_times)

        self._load_mods_started()

        current_mod = self.settings.play_time_mod
        # VB guards on pd.IsLoaded; a populated ModList is the headless equivalent.
        if len(self.pd.mod_list) > 0 and current_mod:
            if current_mod not in self.pdi.play_times:
                self.pdi.play_times[current_mod] = self.settings.play_time
                self.save()
            elif self.pdi.play_times[current_mod] > self.settings.play_time:
                self.settings.play_time = self.pdi.play_times[current_mod]
                self.settings.save()

        self._load_pending()

    def _load_mods_started(self) -> None:
        self.mods_started = CIStrDict()
        data = read_json(self._mods_started_file, default=None)
        if not data:
            return
        for name, iso in data.items():
            dt = _parse_dt(iso)
            if dt is not None:
                self.mods_started[name] = dt

    def _load_pending(self) -> None:
        self.pending_play_times = CIStrDict()
        data = read_json(self._pending_file, default=None)
        if not data:
            return
        for name, records in data.items():
            self.pending_play_times[name] = [_pti_from_dict(r) for r in records]

    def save(self) -> None:
        """Persist the PlayData database and the ModsStarted map."""
        _save_play_data(self._play_data_file, self.pdi)
        self.save_mods_started()

    def save_mods_started(self) -> None:
        write_json(
            self._mods_started_file,
            {name: dt.isoformat() for name, dt in self.mods_started.items()},
        )

    def _save_pending(self) -> None:
        write_json(
            self._pending_file,
            {
                name: [_pti_to_dict(pti) for pti in records]
                for name, records in self.pending_play_times.items()
            },
        )

    # -- Totals accessors -------------------------------------------------- #
    @property
    def total_played(self) -> timedelta:
        return self.pdi.total_played

    @property
    def total_today(self) -> timedelta:
        return self.pdi.total_today

    @property
    def most_in_one_day(self) -> timedelta:
        return self.pdi.most_in_one_day

    @property
    def last_played(self) -> str:
        return self.pdi.last_played

    def play_time(self, mod_name: str) -> timedelta:
        return self.pdi.play_times.get(mod_name, timedelta(0))

    def start_date(self, mod_name: str) -> datetime | None:
        return self.mods_started.get(mod_name)

    def set_start_date(self, mod_name: str, value: datetime) -> None:
        self.mods_started[mod_name] = value

    @property
    def start_dates_recorded(self) -> bool:
        return len(self.mods_started) > 0

    # -- Recording --------------------------------------------------------- #
    def set_play_time(self, mod_name: str, played: timedelta) -> None:
        self.pdi.play_times[mod_name] = played

    def apply_logged_times(self, result: ClientLogResult) -> None:
        """Fold a parsed client-log session into the play-time totals (AddLoggedTimes).

        ``ModsStarted`` is already updated by the log parse; this applies the
        per-mod durations (or the whole-session execution time when nothing was
        attributed) to the totals.
        """
        if not result.mods_loaded:
            self.pdi.total_today += result.execution_time
            self.pdi.total_played += result.execution_time
            if self.pdi.total_today > self.pdi.most_in_one_day:
                self.pdi.most_in_one_day = self.pdi.total_today
            return
        for mod_name, span in result.mods_loaded.items():
            if mod_name in self.pdi.play_times:
                self.pdi.play_times[mod_name] += span
            else:
                self.pdi.play_times[mod_name] = span
            self.pdi.total_today += span
            self.pdi.total_played += span
        if self.pdi.total_today > self.pdi.most_in_one_day:
            self.pdi.most_in_one_day = self.pdi.total_today

    def add_time(self, mod_name: str, played: timedelta) -> None:
        if mod_name == "":
            log.debug("AddTime for blank mod name ignored")
            return
        if mod_name in self.pdi.play_times:
            self.pdi.play_times[mod_name] += played
        else:
            self.pdi.play_times[mod_name] = played
        self.pdi.total_today += played
        self.pdi.total_played += played
        if self.pdi.total_today > self.pdi.most_in_one_day:
            self.pdi.most_in_one_day = self.pdi.total_today

    def reset_time(self, mod_name: str) -> None:
        if mod_name == "":
            log.debug("ResetTime for blank mod name ignored")
            return
        played = self.pdi.play_times.get(mod_name)
        if played is None:
            log.debug("ResetTime for undefined mod name ignored: %s", mod_name)
            return
        self.pdi.play_times[mod_name] = timedelta(0)
        self.pdi.total_today = max(timedelta(0), self.pdi.total_today - played)
        self.pdi.total_played = max(timedelta(0), self.pdi.total_played - played)

    def _clear_current_if(self, mod_name: str) -> None:
        if self.settings.play_time_mod == mod_name:
            self.settings.play_time_mod = ""
            self.settings.play_time = timedelta(0)

    def rename_mod(self, old_name: str, new_name: str) -> None:
        """Move play-time / start-date records from ``old_name`` to ``new_name``."""
        started = self.mods_started
        mods_started_save = False
        if old_name in started:
            if new_name not in started or started[old_name] > started[new_name]:
                started[new_name] = started[old_name]
            del started[old_name]
            mods_started_save = True

        times = self.pdi.play_times
        if old_name in self.pdi.play_times:
            if new_name not in times or times[old_name] > times[new_name]:
                self.pdi.play_times[new_name] = self.pdi.play_times[old_name]
            del self.pdi.play_times[old_name]
            if self.settings.play_time_mod == old_name:
                self.settings.play_time_mod = new_name
                if self.pdi.play_times[new_name] != self.settings.play_time:
                    self.settings.play_time = self.pdi.play_times[new_name]
                self.settings.save()
            self.save()
        elif mods_started_save:
            self.save_mods_started()

        # Rename the Game Play Time file heading text.
        current_filename = self.filename
        self.filename = self.ctx.play_time_file(new_name)
        if not self.filename.is_file():
            self.filename = current_filename
            return
        records: list[PlayTimeInfo] = []
        if self._get_play_times(records) == RecordResult.READ_ERROR:
            log.debug("RenameMod read error: %s", self.filename)
        elif self._save_play_times(new_name, records, log_play_time=False) == (
            RecordResult.WRITE_ERROR
        ):
            log.debug("RenameMod write error: %s", self.filename)
        self.filename = current_filename

    def record_time(self, mod_name: str) -> RecordResult:
        """Record play time for a mod if it meets the minimum (``RecordTime``)."""
        time_played = self.pdi.play_times.get(mod_name)
        if time_played is None:
            self.result = RecordResult.NO_TIME
            return self.result
        if time_played.total_seconds() < self.settings.config_min_play_time * 60:
            self.pdi.play_times.pop(mod_name, None)
            self._clear_current_if(mod_name)
            self.result = RecordResult.NO_TIME
            return self.result

        play_times = [
            PlayTimeInfo(
                to_date_string(datetime.now()),
                self.format_time(time_played, ""),
                self.user_name,
                time_played,
            )
        ]

        # A mod not in the current profile is deferred to PendingPlayTimes.
        if not self.pd.mod_exists(mod_name):
            pti: PlayTimeInfo | None = play_times[0].clone()
            if mod_name not in self.pending_play_times:
                self.pending_play_times[mod_name] = [pti]
            elif pti not in self.pending_play_times[mod_name]:
                if pti.play_time_span > self.pending_play_times[mod_name][0].play_time_span:
                    self.pending_play_times[mod_name] = [pti]
            else:
                pti = None
            if pti is not None:
                self._save_pending()
            self.pdi.play_times.pop(mod_name, None)
            self._clear_current_if(mod_name)
            self.result = RecordResult.NO_TIME
            return self.result

        self.filename = self.ctx.play_time_file(mod_name)
        if self._get_play_times(play_times) == RecordResult.READ_ERROR:
            return self.result

        if self._save_play_times(mod_name, play_times) < RecordResult.NO_TIME:
            self.pdi.play_times.pop(mod_name, None)
            self._clear_current_if(mod_name)

        self.on_contents_refreshed(mod_name, self.filename)
        if not _contains_ci(self.recorded_games, mod_name):
            self.recorded_games.append(mod_name)
        return self.result

    # -- Pending / completed ---------------------------------------------- #
    @property
    def pending_mod_count(self) -> int:
        self.record_completed_games()
        return len(self.pending_play_times)

    def get_pending_play_times(self) -> dict[str, list[PlayTimeInfo]]:
        """Sorted copy of the pending play times (``GetPendingPlayTimes``)."""
        if not self.pending_play_times:
            return {}
        self.record_completed_games()
        pending: dict[str, list[PlayTimeInfo]] = {}
        for name in sorted(self.pending_play_times.keys()):
            records = [pti.clone() for pti in self.pending_play_times[name]]
            sort_play_times(records)
            pending[name] = records
        return pending

    def clear_pending_play_times(self) -> None:
        self.pending_play_times = CIStrDict()
        self._save_pending()

    def record_completed_games(self) -> None:
        """Write pending play times for mods now present in the profile."""
        if not self.pending_play_times:
            return
        current_filename = self.filename
        completed_mods: list[str] = []
        misnamed_mods: list[str] = []
        for name in list(self.pending_play_times.keys()):
            if not self.pd.mod_exists(name):
                continue
            records = [pti.clone() for pti in self.pending_play_times[name]]

            # Mod absent under another profile but present here: apply pending.
            if name in self.pdi.play_times and self.pdi.play_times[name] == timedelta(0):
                self.pdi.play_times[name] = records[-1].play_time_span
                self.pending_play_times[name].pop()
                if self.settings.play_time_mod == name:
                    self.settings.play_time = self.pdi.play_times[name]
                if not self.pending_play_times[name]:
                    misnamed_mods.append(name)
                continue

            if name == self.settings.play_time_mod:
                # Game still active (switching profiles): don't record yet.
                misnamed_mods.append(name)
            elif self._record_completed_game(name, records):
                completed_mods.append(name)

        for name in misnamed_mods:
            self.pending_play_times.pop(name, None)
        for name in completed_mods:
            self.pending_play_times.pop(name, None)

        if completed_mods or misnamed_mods:
            self._save_pending()
            if misnamed_mods:
                self.save()
        self.filename = current_filename

    def _record_completed_game(
        self, mod_name: str, play_times: list[PlayTimeInfo]
    ) -> bool:
        self.filename = self.ctx.play_time_file(mod_name)
        if self._get_play_times(play_times) == RecordResult.READ_ERROR:
            return False
        if self._save_play_times(mod_name, play_times) < RecordResult.NO_TIME and (
            not _contains_ci(self.recorded_games, mod_name)
        ):
            self.recorded_games.append(mod_name)
        self.on_contents_refreshed(mod_name, self.filename)
        return self.result < RecordResult.NO_TIME

    # -- RTF play-time files ---------------------------------------------- #
    def read_play_time_file(
        self, mod_name: str, play_times: list[PlayTimeInfo]
    ) -> RecordResult:
        """Read a mod's play-time file into ``play_times`` (``ReadPlayTimeFile``)."""
        self.result = RecordResult.NO_TIME
        self.filename = self.ctx.play_time_file(mod_name)
        if not self.filename.is_file():
            return RecordResult.NO_TIME
        if self._get_play_times(play_times) == RecordResult.READ_ERROR:
            log.debug("Play Time File read error: %s", self.filename)
        return self.result

    def rebuild_play_time_file(self, mod_name: str) -> RecordResult:
        """Re-write a mod's play-time file from its own contents (fix alignment)."""
        records: list[PlayTimeInfo] = []
        if self.read_play_time_file(mod_name, records) != RecordResult.UPDATED:
            return self.result
        self.result = self._save_play_times(mod_name, records, log_play_time=False)
        if self.result == RecordResult.WRITE_ERROR:
            log.debug("Rebuild play time file write error: %s", self.filename)
        return self.result

    def _get_play_times(self, play_times: list[PlayTimeInfo]) -> RecordResult:
        """Append existing records from the RTF file at ``self.filename``."""
        assert self.filename is not None
        if not self.filename.is_file():
            self.result = RecordResult.CREATED
            return self.result
        try:
            text = read_rtf_text(self.filename.read_text(encoding="utf-8", errors="replace"))
        except OSError as ex:
            log.warning("Unable to read play time file %s: %s", self.filename, ex)
            self.result = RecordResult.READ_ERROR
            return self.result
        for entry in text.split("\n"):
            if len(entry) > 38 and entry[:3].strip().isdigit():
                fields = re.sub(" {2,}", "\t", entry).split("\t")
                if len(fields) >= 3:
                    play_times.append(PlayTimeInfo(fields[0], fields[1], fields[2]))
        self.result = RecordResult.UPDATED
        return self.result

    def _save_play_times(
        self, mod_name: str, play_times: list[PlayTimeInfo], *, log_play_time: bool = True
    ) -> RecordResult:
        """Write ``play_times`` as the mod's RTF play-time file (``SavePlayTimes``)."""
        if not play_times:
            return self.result
        assert self.filename is not None

        sort_play_times(play_times)
        lines = [
            f"{pti.completed}    {pti.play_time:<19}    {pti.user_name}"
            for pti in play_times
        ]
        lines = list(dict.fromkeys(lines))  # distinct, order-preserving

        if log_play_time and lines:
            log.debug("SavePlayTimes(%s): %s", mod_name, lines[0])

        self._update_completed_info(self.pd.mod_item(mod_name), play_times, lines)

        body = [
            mod_name,
            "",
            "Completed      Time Played            User",
            *lines,
        ]
        try:
            self.filename.parent.mkdir(parents=True, exist_ok=True)
            self.filename.write_text(write_rtf(body), encoding="utf-8")
        except OSError as ex:
            log.warning("Unable to record play time file %s: %s", self.filename, ex)
            self.result = RecordResult.WRITE_ERROR
        return self.result

    def _update_completed_info(
        self, mdi: ModData | None, play_times: list[PlayTimeInfo], lines: list[str]
    ) -> None:
        """Update the mod's DateCompleted / CompletedCount (``UpdateCompletedInfo``)."""
        if mdi is None:
            return
        completed_count = sum(
            1 for line in lines if line.lower().endswith(self.user_name.lower())
        )
        if mdi.completed_count == completed_count:
            return
        for pti in play_times:
            if pti.user_name == self.user_name:
                date_completed = parse_date_string(pti.completed)
                if date_completed is not None:
                    mdi.date_completed = date_completed
                break
        mdi.completed_count = completed_count
        self.on_save_mods()

    # -- Validation / deletion -------------------------------------------- #
    def validate(self, games_backup_dir: Path) -> None:
        """Reconcile play times against the game-save backups (``ValidatePlayData``)."""
        mod_list: list[str] = []
        if self.settings.play_time_mod:
            mod_list.append(self.settings.play_time_mod)

        save_data = False
        if games_backup_dir.is_dir():
            for backup in sorted(p for p in games_backup_dir.iterdir() if p.is_dir()):
                backup_mod = self.to_mod_key(backup.name)
                if backup_mod:
                    if backup_mod not in self.pdi.play_times:
                        self.pdi.play_times[backup_mod] = timedelta(0)
                        save_data = True
                    mod_list.append(backup_mod)

        removed_pending = False
        for key in mod_list:
            if key in self.pending_play_times:
                pending_span = self.pending_play_times[key][0].play_time_span
                if pending_span > self.pdi.play_times.get(key, timedelta(0)):
                    self.pdi.play_times[key] = pending_span
                    save_data = True
                del self.pending_play_times[key]
                removed_pending = True
        if removed_pending:
            self._save_pending()

        record_list = [
            key for key in self.pdi.play_times if not _contains_ci(mod_list, key)
        ]
        remove_list: list[str] = []
        for key in record_list:
            self.record_time(key)
            if key in self.pdi.play_times:
                remove_list.append(key)
        for key in remove_list:
            self.pdi.play_times.pop(key, None)
            self.mods_started.pop(key, None)

        if save_data or remove_list:
            self.save()

    def record_deleted_games(
        self, games_backup_dir: Path, current_save_names: list[str]
    ) -> None:
        """Record play time for mods whose game saves have all been deleted.

        ``current_save_names`` is the caller-supplied set of save names still present
        in the NWN saves folder (from :class:`~vaultkeeper.game.game_saves.GameSaves`);
        the first is treated as the current game (VB ``NwGs.CurrentGameSave``).
        """
        if not self.pdi.play_times:
            return

        backup_list: list[str] = []
        if games_backup_dir.is_dir():
            for backup in sorted(p for p in games_backup_dir.iterdir() if p.is_dir()):
                backup_mod = self.to_mod_key(backup.name)
                if backup_mod and not _contains_ci(backup_list, backup_mod):
                    backup_list.append(backup_mod)

        current = current_save_names[0] if current_save_names else ""
        for save_name in current_save_names[1:]:
            game = self.to_mod_key(save_name)
            if game and not _contains_ci(backup_list, game):
                backup_list.append(game)
        current_mod = self.to_mod_key(current)

        self.deleted_games = []
        for game in self.pdi.play_times:
            if not _contains_ci(backup_list, game) and (
                not current_mod or game != current_mod
            ):
                self.deleted_games.append(game)

        for game in self.deleted_games:
            self.record_time(game)
            self.mods_started.pop(game, None)

    # -- Formatting -------------------------------------------------------- #
    def format_time(
        self, played: timedelta, desc: str = "Mod played for", zero: str = ""
    ) -> str:
        """Format a duration as ``n,nnn hours n minutes`` (``FormatTime``)."""
        if played.total_seconds() < 60:
            secs = int(played.total_seconds())
            if secs == 0 and zero != "":
                return zero
            if self.pdi.total_played.total_seconds() == 0:
                return "NWN not played"
            if secs == 0:
                return "Mod play time unknown"
            return f"{desc} {secs} secs" if desc else f"{secs} secs"

        parts: list[str] = []
        if desc:
            parts.append(desc)
        played_hours = played.days * 24 + played.seconds // 3600
        minutes = (played.seconds % 3600) // 60
        if played_hours > 0:
            parts.append(to_plural(played_hours, "hour"))
        if minutes > 0:
            parts.append(to_plural(minutes, "min"))
        return " ".join(parts).rstrip()

    def format_days(
        self, played: timedelta, desc: str = "NWN played for", zero: str = ""
    ) -> str:
        """Format a duration as years/weeks/days/hours/minutes (``FormatDays``)."""
        if played.total_seconds() < 60:
            if zero == "":
                zero = (
                    "NWN not played"
                    if self.pdi.total_played.total_seconds() == 0
                    else "Mod play time unknown"
                )
            return zero

        parts: list[str] = []
        if desc:
            parts.append(desc)
        played_hours = played.days * 24 + played.seconds // 3600
        minutes = (played.seconds % 3600) // 60
        factor = self.settings.config_day_conversion_factor or 24
        played_days = played_hours // factor
        played_hours -= played_days * factor

        if played_days > 365:
            years = played_days // 365
            parts.append(to_plural(years, "year"))
            played_days -= years * 365
        if played_days > 7:
            weeks = played_days // 7
            parts.append(to_plural(weeks, "week"))
            played_days -= weeks * 7
        if played_days > 0:
            parts.append(to_plural(played_days, "day"))
        if played_hours > 0:
            parts.append(to_plural(played_hours, "hour"))
        if minutes > 0:
            parts.append(to_plural(minutes, "min"))
        return " ".join(parts).rstrip()


# ------------------------------------------------------------------------- #
# Persistence helpers (native JSON for the play-time database)
# ------------------------------------------------------------------------- #
def _load_play_data(path: Path) -> PlayData:
    data = read_json(path, default=None)
    pd = PlayData()
    if not data:
        return pd
    pd.total_played = _parse_td(data.get("total_played"))
    pd.total_today = _parse_td(data.get("total_today"))
    pd.most_in_one_day = _parse_td(data.get("most_in_one_day"))
    pd.last_played = data.get("last_played", pd.last_played)
    pd.play_times = CIStrDict(
        {name: _parse_td(secs) for name, secs in data.get("play_times", {}).items()}
    )
    return pd


def _save_play_data(path: Path, pd: PlayData) -> None:
    write_json(
        path,
        {
            "total_played": pd.total_played.total_seconds(),
            "total_today": pd.total_today.total_seconds(),
            "most_in_one_day": pd.most_in_one_day.total_seconds(),
            "last_played": pd.last_played,
            "play_times": {
                name: span.total_seconds() for name, span in pd.play_times.items()
            },
        },
    )


def _pti_to_dict(pti: PlayTimeInfo) -> dict:
    return {
        "completed": pti.completed,
        "play_time": pti.play_time,
        "user_name": pti.user_name,
        "play_time_span": pti.play_time_span.total_seconds(),
    }


def _pti_from_dict(data: dict) -> PlayTimeInfo:
    return PlayTimeInfo(
        data.get("completed", ""),
        data.get("play_time", ""),
        data.get("user_name", ""),
        timedelta(seconds=data.get("play_time_span", 0)),
    )


def _parse_td(value: object) -> timedelta:
    if isinstance(value, (int, float)):
        return timedelta(seconds=value)
    return timedelta(0)


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _contains_ci(items: list[str], target: str) -> bool:
    low = target.lower()
    return any(item.lower() == low for item in items)
