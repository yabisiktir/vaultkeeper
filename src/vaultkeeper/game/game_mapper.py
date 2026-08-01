"""GameMapper — maps NWN save-game / logged module names to NIT mod names.

Faithful headless port of ``GameMapper.vb`` (+ its ``.Defs/.Internal/.Workers/
.ModFileInfo/.SaveNameInfo/.UserResponses`` partials). This is the play-loop spine:
play-time attribution needs to turn a raw ``.sav`` name or a "Loading Module:" log
entry back into the user's mod name.

The **resolution ladder** (preserved exactly):

1. installed ``.mod``/``.nwm`` file keys in the profile database, then
2. those keys' non-default installers' conflict lists filtered to *installed* mods,
3. patch-file exclusion (``is_not_patch`` + original-campaign patch sets),
4. a single surviving hit wins; multiple hits ask the user (remembered by type),
5. the cross-profile ``SaveNames`` dictionary (built by scanning every profile's mod
   files), asking which profile when ambiguous,
6. finally a user-typed name via the name editor.

Concerns that were UI in the VB app (the choice dialog, the name editor, the profile
picker) are injected through :class:`GameMapperPrompter`. Reading a module's save
name/description out of a ``.mod``/``.nwm`` is injected through
:class:`ModuleInfoReader` (the ERF/``module.ifo`` decode lives behind that seam).
Persistence is native JSON (hybrid strategy), not the VB BinaryFormatter files.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
from pathlib import Path
from typing import Protocol

from nwnfile.log import get_logger

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.persistence.json_store import read_json, write_json

log = get_logger(__name__)

#: Returned as the save name when a module read fails (``GameMapper.UnknownSaveName``).
UNKNOWN_SAVE_NAME = "Unable to retrieve the Game Save Name"
#: Returned as the description when a module read fails (``GameMapper.ReadFailureText``).
READ_FAILURE_TEXT = "- Unable to retrieve Mod Details."
#: The GameSaves "no saves" placeholder (kept local to avoid a game.game_saves cycle).
NO_SAVES_TEXT = "No games have been saved"

#: The original-campaign module sets. A campaign ``.nwm`` is treated as a *patch*
#: (ignored when picking a mod name) only when all the other files of its campaign
#: sit beside it — i.e. it's a genuine original-campaign file, not a user mod.
_CAMPAIGNS: dict[str, list[str]] = {
    "NWN": [
        "Chapter1.nwm", "Chapter1E.nwm", "Chapter2.nwm", "Chapter2E.nwm",
        "Chapter3.nwm", "Chapter4.nwm", "Prelude.nwm",
    ],
    "SOU": ["XP1-Chapter 1.nwm", "XP1-Chapter 2.nwm", "XP1-Interlude.nwm"],
    "HOU": ["XP2_Chapter1.nwm", "XP2_Chapter2.nwm", "XP2_Chapter3.nwm"],
}

#: Group/mod-name fragments that mark a patch (all lower-case, per the VB lists).
_PATCH_START = ("cpp ", "patch ", "fix ")
_PATCH_END = (" cpp", " patch", " fix")
_PATCH_NAMES = (" patch ", "hotfix", " fix ", "community patch")


def _build_patch_files() -> dict[str, list[str]]:
    """PatchFiles: each campaign file -> the other files of the same campaign."""
    patch_files: dict[str, list[str]] = {}
    for files in _CAMPAIGNS.values():
        for i, name in enumerate(files):
            patch_files[name.lower()] = [f for j, f in enumerate(files) if j != i]
    return patch_files


_PATCH_FILES = _build_patch_files()


# ------------------------------------------------------------------------- #
# Injected seams
# ------------------------------------------------------------------------- #
@dataclass
class ModuleInfo:
    """The bits of a module file GameMapper needs (from ``module.ifo``/ERF)."""

    save_name: str = UNKNOWN_SAVE_NAME
    description: str = READ_FAILURE_TEXT
    #: The module's own filename (used only for the ``_DEMO`` save-name fallback).
    mod_filename: str = ""


class ModuleInfoReader(Protocol):
    """Reads a module's save name/description from a ``.mod``/``.nwm`` file."""

    def read(self, path: Path) -> ModuleInfo | None:  # pragma: no cover - protocol
        ...


class GameMapperPrompter(Protocol):
    """UI hooks GameMapper falls back to when resolution is ambiguous."""

    def choose_mod(self, mod_list: list[str]) -> str:  # pragma: no cover
        """Pick one mod name from several equally-valid candidates."""
        ...

    def specify_mod_name(
        self, identifier: str, message: str
    ) -> tuple[bool, str]:  # pragma: no cover
        """Ask the user to type a mod name. Return ``(ok, name)``; ``ok=False``
        means "use the identifier as-is" (the VB Cancel path)."""
        ...

    def choose_profile(
        self, message: str, options: list[str]
    ) -> int:  # pragma: no cover
        """Pick which profile the play session belonged to. Return an index."""
        ...


class DefaultPrompter:
    """Non-interactive prompter: takes the first candidate, never invents a name.

    Suitable for headless/automated resolution. The real app injects a Qt-backed
    prompter that shows the choice dialog / name editor / profile picker.
    """

    def choose_mod(self, mod_list: list[str]) -> str:
        return mod_list[0] if mod_list else ""

    def specify_mod_name(self, identifier: str, message: str) -> tuple[bool, str]:
        return (False, identifier)

    def choose_profile(self, message: str, options: list[str]) -> int:
        return 0


# ------------------------------------------------------------------------- #
# Records
# ------------------------------------------------------------------------- #
class ResponseType(IntEnum):
    CHOICE = 0
    LOG = 1
    SAV = 2
    PROFILE = 3


@dataclass
class ModFileInfo:
    """Per-mod-file record inside a :class:`SaveNameInfo` (``GameMapper.ModFileInfo``)."""

    save_name: str = ""
    description: str = ""
    profile: str = ""
    mod_name: str = ""
    mod_updated: datetime = datetime.min

    def clone(self) -> ModFileInfo:
        return ModFileInfo(
            self.save_name, self.description, self.profile, self.mod_name, self.mod_updated
        )


class SaveNameInfo:
    """The mod files that share a single save name (``GameMapper.SaveNameInfo``)."""

    def __init__(self) -> None:
        #: full mod-file path -> ModFileInfo (case-insensitive on the path key).
        self.mod_files: dict[str, ModFileInfo] = {}

    def add(
        self, full_name: str, info: ModuleInfo, date_updated: datetime, profiles_dir: Path
    ) -> None:
        """Add a mod file, deriving profile/mod-name from its path under Profiles."""
        # Match VB's plain prefix strip: do NOT follow symlinks (a symlinked store
        # or a mod file symlinked into the tree must still map to its profile).
        rel = None
        try:
            rel = Path(full_name).relative_to(profiles_dir)
        except ValueError:
            try:
                rel = Path(full_name).resolve().relative_to(profiles_dir.resolve())
            except ValueError:
                rel = None
        if rel is not None and len(rel.parts) >= 2:
            profile, mod_name = rel.parts[0], rel.parts[1]
        else:
            profile, mod_name = "", ""
        self.mod_files[full_name] = ModFileInfo(
            save_name=info.save_name,
            description=info.description,
            profile=profile,
            mod_name=mod_name,
            mod_updated=date_updated,
        )

    def clone(self) -> SaveNameInfo:
        sni = SaveNameInfo()
        for key, value in self.mod_files.items():
            sni.mod_files[key] = value.clone()
        return sni


class UserResponses:
    """Remembered answers to GameMapper's ambiguity prompts (``UserResponses``)."""

    def __init__(self) -> None:
        self.mod_choices: list[str] = []
        self.log_to_mod_names: dict[str, str] = {}
        self.sav_to_mod_names: dict[str, str] = {}
        self.profile_choices: dict[str, str] = {}

    def add(self, identifier: str, mod_name: str, response_type: ResponseType) -> str:
        """Record a resolved answer of the given type and return the mod name."""
        if response_type == ResponseType.LOG:
            self.log_to_mod_names[identifier] = mod_name
        elif response_type == ResponseType.SAV:
            self.sav_to_mod_names[identifier] = mod_name
        elif response_type == ResponseType.PROFILE:
            self.profile_choices[identifier] = mod_name
        else:
            log.warning(
                "UserResponses.add: invalid response type (%s, %s, %s)",
                identifier, mod_name, response_type,
            )
        return mod_name

    def add_choice(self, mod_name: str) -> None:
        self.mod_choices.append(mod_name)

    def rename_mod(self, old_name: str, new_name: str) -> bool:
        """Point every remembered answer for ``old_name`` at ``new_name``."""
        updated = False
        if old_name in self.mod_choices:
            self.mod_choices = [
                new_name if n == old_name else n for n in self.mod_choices
            ]
            updated = True
        for table in (self.log_to_mod_names, self.sav_to_mod_names, self.profile_choices):
            for key, value in list(table.items()):
                if value == old_name:
                    table[key] = new_name
                    updated = True
        return updated

    def to_dict(self) -> dict:
        return {
            "mod_choices": self.mod_choices,
            "log_to_mod_names": self.log_to_mod_names,
            "sav_to_mod_names": self.sav_to_mod_names,
            "profile_choices": self.profile_choices,
        }

    @classmethod
    def from_dict(cls, data: dict) -> UserResponses:
        ur = cls()
        ur.mod_choices = list(data.get("mod_choices", []))
        ur.log_to_mod_names = dict(data.get("log_to_mod_names", {}))
        ur.sav_to_mod_names = dict(data.get("sav_to_mod_names", {}))
        ur.profile_choices = dict(data.get("profile_choices", {}))
        return ur


@dataclass
class GameMapperContext:
    """Where GameMapper looks for profiles and stores its cache."""

    profiles_dir: Path
    active_profile: str
    data_dir: Path
    installer_dir_name: str = C.MOD_INSTALLER_DIR
    mod_folder: str = C.MOD_FOLDER
    mod_nwm_folder: str = C.MOD_NWM_FOLDER


# ------------------------------------------------------------------------- #
# The mapper
# ------------------------------------------------------------------------- #
class GameMapper:
    """Resolve save-game / logged module names to NIT mod names."""

    #: A rebuild is considered "current" for this long (VB FileScanCurrent = 10s).
    REFRESH_INTERVAL = timedelta(seconds=10)

    def __init__(
        self,
        pd: ProfileData,
        ctx: GameMapperContext,
        *,
        module_reader: ModuleInfoReader,
        prompter: GameMapperPrompter | None = None,
        save_name_rules: dict[str, str] | None = None,
        save_name_removed_chars: str = "",
        auto_scan: bool = True,
    ) -> None:
        self.pd = pd
        self.ctx = ctx
        self.module_reader = module_reader
        self.prompter = prompter or DefaultPrompter()
        #: VaultDownloadRules save-name rules (Phase 6); empty until wired.
        self.save_name_rules = save_name_rules or {}
        self.save_name_removed_chars = save_name_removed_chars

        self.save_names: dict[str, SaveNameInfo] = {}
        self.save_name_map: dict[str, str] = {}
        self.user_choices = UserResponses()
        self._last_refresh = datetime.min
        self._scanning = False
        self._empty_profile = False

        self._load_user_choices()
        if not self._load():
            if auto_scan:
                self.refresh(force=True)
        else:
            self.create_map_entries()

    # -- Persistence ------------------------------------------------------- #
    @property
    def _map_data_file(self) -> Path:
        return self.ctx.data_dir / "GameMapData.json"

    @property
    def _choices_file(self) -> Path:
        return self.ctx.data_dir / "GameMapChoices.json"

    def _load(self) -> bool:
        data = read_json(self._map_data_file, default=None)
        if not data:
            return False
        self.save_names = {}
        for save_name, sni_data in data.items():
            sni = SaveNameInfo()
            for path, mfi in sni_data.get("mod_files", {}).items():
                sni.mod_files[path] = ModFileInfo(
                    save_name=mfi.get("save_name", ""),
                    description=mfi.get("description", ""),
                    profile=mfi.get("profile", ""),
                    mod_name=mfi.get("mod_name", ""),
                    mod_updated=_parse_dt(mfi.get("mod_updated")),
                )
            self.save_names[save_name] = sni
        return len(self.save_names) > 0

    def _save(self) -> None:
        data = {
            save_name: {
                "mod_files": {
                    path: {
                        "save_name": mfi.save_name,
                        "description": mfi.description,
                        "profile": mfi.profile,
                        "mod_name": mfi.mod_name,
                        "mod_updated": mfi.mod_updated.isoformat(),
                    }
                    for path, mfi in sni.mod_files.items()
                }
            }
            for save_name, sni in self.save_names.items()
        }
        write_json(self._map_data_file, data)

    def _load_user_choices(self) -> None:
        data = read_json(self._choices_file, default=None)
        if data:
            self.user_choices = UserResponses.from_dict(data)

    def _save_user_choices(self) -> None:
        write_json(self._choices_file, self.user_choices.to_dict())

    # -- Scan / map building ---------------------------------------------- #
    @property
    def file_scan_current(self) -> bool:
        return (datetime.now() - self._last_refresh) < self.REFRESH_INTERVAL

    def reset_refresh_time(self) -> None:
        self._last_refresh = datetime.min

    def refresh(self, *, force: bool = False) -> None:
        """Rebuild the SaveNames dictionary from disk (rate-limited unless forced)."""
        if not force and self.file_scan_current:
            return
        self._scanning = True
        self._empty_profile = False
        self.save_names = {}
        self.scan_profiles()
        self._last_refresh = datetime.now()
        self.create_map_entries()
        self._scanning = False
        self._save()

    def scan_profiles(self) -> None:
        """Populate SaveNames from every profile's mod files (``ScanProfiles``)."""
        profiles = self.ctx.profiles_dir
        if not profiles.is_dir():
            self._empty_profile = True
            return
        for profile in sorted(p for p in profiles.iterdir() if p.is_dir()):
            for installer in self._find_installer_dirs(profile):
                for mod_folder in (self.ctx.mod_folder, self.ctx.mod_nwm_folder):
                    folder = installer / mod_folder
                    if not folder.is_dir():
                        continue
                    for mod_file in sorted(f for f in folder.iterdir() if f.is_file()):
                        self._scan_mod_file(mod_file)
        self._empty_profile = len(self.save_names) == 0

    def _find_installer_dirs(self, profile: Path) -> Iterable[Path]:
        name = self.ctx.installer_dir_name
        for path in profile.rglob("*"):
            if path.is_dir() and path.name == name:
                yield path

    def _scan_mod_file(self, mod_file: Path) -> None:
        if self._mod_file_exists(mod_file) or self.ignore_mod_file(mod_file):
            return
        info = self.module_reader.read(mod_file)
        if info is None:
            return
        save_name = info.save_name
        if save_name == "_DEMO":
            stem = Path(info.mod_filename or mod_file.name).stem
            save_name = stem
        try:
            mtime = datetime.fromtimestamp(mod_file.stat().st_mtime)
        except OSError:
            mtime = datetime.min
        self.save_names.setdefault(save_name, SaveNameInfo()).add(
            str(mod_file), info, mtime, self.ctx.profiles_dir
        )

    def _mod_file_exists(self, mod_file: Path) -> bool:
        """True if this exact path is already recorded and up to date."""
        try:
            mtime = datetime.fromtimestamp(mod_file.stat().st_mtime)
        except OSError:
            return False
        path = str(mod_file)
        for sni in self.save_names.values():
            mfi = sni.mod_files.get(path)
            if mfi is not None:
                return mfi.mod_updated == mtime
        return False

    def ignore_mod_file(self, mod_file: Path) -> bool:
        """True if this file is an original-campaign patch member or a CPP file."""
        required = _PATCH_FILES.get(mod_file.name.lower())
        if required is None:
            return False
        parent = mod_file.parent
        for req in required:
            if not (parent / req).is_file():
                return True
        parts_lower = [p.lower() for p in mod_file.parts]
        return any(
            p.startswith("cpp ") or p.startswith("community patch") for p in parts_lower
        )

    def create_map_entries(self) -> None:
        """Build SaveNameMap from SaveNames + the download-rule save-name rules."""
        self.save_name_map = {}
        for key in self.save_names:
            map_key = key.rstrip(".")
            for ch in self.save_name_removed_chars:
                map_key = map_key.replace(ch, "")
            if key != map_key and map_key not in self.save_name_map:
                self.save_name_map[map_key] = key

        redundant = 0
        for rule_key, rule_value in self.save_name_rules.items():
            if rule_key in self.save_name_map:
                redundant += 1
            else:
                self.save_name_map[rule_key] = rule_value
        if redundant:
            log.info("Redundant save-name rules detected: %d", redundant)

        removed_any = False
        for key in list(self.save_name_map.keys()):
            if key in self.user_choices.sav_to_mod_names:
                del self.user_choices.sav_to_mod_names[key]
                removed_any = True
        if removed_any:
            self._save_user_choices()

    # -- Description ------------------------------------------------------- #
    def get_mod_description(self, mod_file: Path) -> str:
        """The description for a mod file (from the cache, refreshing if stale)."""
        path = str(mod_file)
        try:
            mtime = datetime.fromtimestamp(mod_file.stat().st_mtime)
        except OSError:
            mtime = datetime.min
        if not self._scanning:
            for sni in self.save_names.values():
                mfi = sni.mod_files.get(path)
                if mfi is not None:
                    if mfi.mod_updated != mtime:
                        info = self.module_reader.read(mod_file)
                        mfi.description = (
                            info.description if info else READ_FAILURE_TEXT
                        )
                        mfi.mod_updated = mtime
                        self._save()
                    return mfi.description
        info = self.module_reader.read(mod_file)
        return info.description if info else READ_FAILURE_TEXT

    # -- Resolution: logged module name ----------------------------------- #
    def log_name_to_mod_name(self, module_name: str) -> str:
        """Resolve a "Loading Module:" log name to a NIT mod name."""
        mod_file_name = f"{module_name}{C.EXT_MOD}"
        key_list = [
            fk for fk in self.pd.installed_list if fk.filename.lower() == mod_file_name.lower()
        ]
        if not key_list:
            nwm_name = f"{module_name}{C.EXT_NWM}"
            key_list = [
                fk for fk in self.pd.installed_list if fk.filename.lower() == nwm_name.lower()
            ]
            if key_list:
                mod_file_name = nwm_name

        # Installed, non-default installers' conflict keys for installed mods.
        mod_key_list: list[FileKeyInfo] = []
        for fk in key_list:
            ifd = self.pd.installed_item(fk)
            if ifd is not None and not ifd.is_default_installer:
                for mfk in ifd.mod_file_conflicts:
                    md = self.pd.mod_item(mfk.mod_name)
                    if md is not None and md.installed:
                        mod_key_list.append(mfk)

        if len(mod_key_list) == 1:
            return mod_key_list[0].mod_name

        mod_list = [mfk.mod_name for mfk in mod_key_list if self.is_not_patch(mfk)]
        if len(mod_list) == 1:
            return mod_list[0]
        if len(mod_list) > 1:
            return self._ask_user(mod_list)
        if len(mod_key_list) > 1:
            return self._ask_user([mfk.mod_name for mfk in mod_key_list])

        # Fall through to the cross-profile SaveNames dictionary.
        mod_list = self.find_mod_names(mod_file_name)
        if not mod_list:
            self.refresh(force=True)
            mod_list = self.find_mod_names(mod_file_name)
        if len(mod_list) == 1:
            return mod_list[0]
        if len(mod_list) > 1:
            return self._ask_user(mod_list)

        name_result = self._get_mod_from_log_filename(mod_file_name)
        if name_result != "":
            return name_result

        if module_name in self.user_choices.log_to_mod_names:
            return self.user_choices.log_to_mod_names[module_name]

        ok, name = self.prompter.specify_mod_name(
            module_name,
            "The game you just played does not have a Mod Installer defined. "
            "Please enter the Mod Name you will use so Vaultkeeper can record play time.",
        )
        result = self.user_choices.add(
            module_name, name if ok else module_name, ResponseType.LOG
        )
        self._save_user_choices()
        return result

    def _get_mod_from_log_filename(self, mod_file_name: str) -> str:
        """Match a mod filename across profiles via the SaveNames dictionary."""
        file_list: list[ModFileInfo] = []
        for sni in self.save_names.values():
            for key, mfi in sni.mod_files.items():
                if Path(key).name.lower() == mod_file_name.lower():
                    file_list.append(mfi)

        if len(file_list) == 1:
            return file_list[0].mod_name
        if not file_list:
            return ""

        profile_names: list[str] = []
        for mfi in file_list:
            if mfi.save_name in self.user_choices.profile_choices:
                return self.user_choices.profile_choices[mfi.save_name]
            if mfi.mod_name in self.user_choices.profile_choices.values():
                result = self.user_choices.add(
                    mfi.save_name, mfi.mod_name, ResponseType.PROFILE
                )
                self._save_user_choices()
                return result
            profile_names.append(f"{mfi.profile} ({mfi.mod_name})")

        idx = self.prompter.choose_profile(
            "Please select which Profile you used when you last played or saved.",
            profile_names,
        )
        result = self.user_choices.add(
            file_list[0].save_name, file_list[idx].mod_name, ResponseType.PROFILE
        )
        self._save_user_choices()
        return result

    # -- Resolution: save-game name --------------------------------------- #
    def save_name_to_mod_name(
        self, save_name: str, *, interactive: bool = True
    ) -> str:
        """Resolve an NWN save-game name (no extension) to a NIT mod name.

        Exit-time play attribution runs with ``interactive=True`` (the default),
        which is where the VB app asks the user to disambiguate. Passive callers
        — e.g. the status-bar "current game" summary — must pass
        ``interactive=False`` so they never pop a blocking prompt; those fall
        back to a remembered answer, the first sensible candidate, or the raw
        save name, and they do not persist a guessed choice.
        """
        if save_name == "" or save_name == NO_SAVES_TEXT:
            return save_name

        info, save_name = self._get_save_info(save_name)

        if info is None:
            if save_name in self.user_choices.sav_to_mod_names:
                return self.user_choices.sav_to_mod_names[save_name]
            if not interactive:
                return save_name
            ok, name = self.prompter.specify_mod_name(
                save_name,
                "A saved game does not have a Mod Installer defined in any profile. "
                "Please enter the Mod Name you will use so Vaultkeeper can record play time.",
            )
            result = self.user_choices.add(
                save_name, name if ok else save_name, ResponseType.SAV
            )
            self._save_user_choices()
            return result

        # Prefer the mod name for the active profile.
        name_list = [
            mfi.mod_name
            for mfi in info.mod_files.values()
            if mfi.profile == self.ctx.active_profile
        ]
        if len(name_list) == 1:
            return name_list[0]

        mod_names = [n for n in name_list if self.is_not_patch(n)]
        if len(mod_names) == 1:
            return mod_names[0]
        if len(mod_names) > 1:
            return self._ask_user(mod_names, interactive=interactive)

        # No active-profile hit: consider all profiles.
        distinct_names = _distinct(mfi.mod_name for mfi in info.mod_files.values())
        if len(distinct_names) == 1:
            return distinct_names[0]

        if save_name in self.user_choices.profile_choices:
            return self.user_choices.profile_choices[save_name]

        profile_names: list[str] = []
        for mfi in info.mod_files.values():
            if mfi.mod_name in self.user_choices.profile_choices.values():
                result = self.user_choices.add(
                    save_name, mfi.mod_name, ResponseType.PROFILE
                )
                self._save_user_choices()
                return result
            profile_names.append(f"{mfi.profile} ({mfi.mod_name})")

        if not interactive:
            # Best passive guess: the first defining profile's mod (matches the
            # DefaultPrompter's "take the first candidate"), without persisting.
            return list(info.mod_files.values())[0].mod_name

        idx = self.prompter.choose_profile(
            "The Mod you are playing is not in the current Profile, but is defined in "
            "others. Please select which Profile you used.",
            profile_names,
        )
        selected = list(info.mod_files.values())[idx].mod_name
        result = self.user_choices.add(save_name, selected, ResponseType.PROFILE)
        self._save_user_choices()
        return result

    def _get_save_info(self, save_name: str) -> tuple[SaveNameInfo | None, str]:
        """Look up save info; returns ``(info, resolved_name)``.

        The name is rewritten when a SaveNameMap rule applies. A full rebuild is
        performed once if the name isn't found and isn't a remembered user answer.
        """
        found = self._lookup_save_info(save_name)
        if found is not None:
            return found
        if self.save_names and save_name in self.user_choices.sav_to_mod_names:
            # Avoid a full scan when the user already answered this save name.
            return None, save_name

        self.refresh(force=True)
        found = self._lookup_save_info(save_name)
        if found is not None:
            return found
        return None, save_name

    def _lookup_save_info(
        self, save_name: str
    ) -> tuple[SaveNameInfo, str] | None:
        if save_name in self.save_names:
            return self.save_names[save_name], save_name
        mapped = self.save_name_map.get(save_name)
        if mapped is not None and mapped in self.save_names:
            return self.save_names[mapped], mapped
        return None

    # -- Predicates -------------------------------------------------------- #
    def is_save_name(self, save_name: str) -> bool:
        return save_name in self.save_names

    def is_mod_name(self, name: str) -> bool:
        if self.pd.mod_exists(name):
            return True
        for sni in self.save_names.values():
            for mfi in sni.mod_files.values():
                if mfi.mod_name.lower() == name.lower():
                    return True
        return False

    def is_not_patch(self, target: FileKeyInfo | str) -> bool:
        """True unless the group/mod name looks like a patch/fix/CPP file."""
        if isinstance(target, FileKeyInfo):
            fields = (target.group.lower(), target.mod_name.lower())
        else:
            fields = (target.lower(),)
        for value in fields:
            if any(value.startswith(p) for p in _PATCH_START):
                return False
            if any(value.endswith(p) for p in _PATCH_END):
                return False
            if any(p in value for p in _PATCH_NAMES):
                return False
        return True

    def find_mod_names(self, mod_file: str) -> list[str]:
        """Installed mod names in the active profile matching this mod filename."""
        mod_list: list[str] = []
        active = self.ctx.active_profile
        for sni in self.save_names.values():
            for key, mfi in sni.mod_files.items():
                if mfi.profile == active and Path(key).name.lower() == mod_file.lower():
                    md = self.pd.mod_item(mfi.mod_name)
                    if md is not None and md.installed:
                        mod_list.append(mfi.mod_name)
        return mod_list

    # -- Prompts ----------------------------------------------------------- #
    def _ask_user(self, mod_list: list[str], *, interactive: bool = True) -> str:
        mod_list = _distinct(mod_list)
        if len(mod_list) == 1:
            return mod_list[0]
        for name in mod_list:
            if name in self.user_choices.mod_choices:
                return name
        if not interactive:
            return mod_list[0]
        selected = self.prompter.choose_mod(mod_list)
        self.user_choices.add_choice(selected)
        self._save_user_choices()
        return selected

    # -- Mutation ---------------------------------------------------------- #
    def clear(self) -> None:
        """Forget the SaveNames dictionary and its cache file."""
        self.save_names = {}
        self._map_data_file.unlink(missing_ok=True)

    def remove_user_response(self, category: str, key: str) -> bool:
        """Forget a remembered user response so the mapper will ask again.

        ``category`` is one of ``mod_choices`` / ``log`` / ``sav`` / ``profile``
        (VB UserResponseEditor's four groups). ``key`` is the mod name for
        ``mod_choices`` and the identifier (log/save name) for the others.
        Persists on removal. Returns True if something was removed.
        """
        uc = self.user_choices
        removed = False
        if category == "mod_choices":
            if key in uc.mod_choices:
                uc.mod_choices = [n for n in uc.mod_choices if n != key]
                removed = True
        else:
            table = {
                "log": uc.log_to_mod_names,
                "sav": uc.sav_to_mod_names,
                "profile": uc.profile_choices,
            }.get(category)
            if table is not None and key in table:
                del table[key]
                removed = True
        if removed:
            self._save_user_choices()
        return removed

    def rename_mod(self, old_name: str, new_name: str) -> None:
        """Rewrite cached mod-file paths and remembered answers for a renamed mod."""
        old_dir = (self.ctx.profiles_dir / self.ctx.active_profile / old_name)
        new_dir = (self.ctx.profiles_dir / self.ctx.active_profile / new_name)
        touched = False
        for sni in self.save_names.values():
            for old_key in list(sni.mod_files.keys()):
                mfi = sni.mod_files[old_key]
                if mfi.profile != self.ctx.active_profile or mfi.mod_name != old_name:
                    continue
                new_key = old_key.replace(str(old_dir), str(new_dir))
                clone = mfi.clone()
                clone.mod_name = new_name
                if new_key not in sni.mod_files:
                    sni.mod_files[new_key] = clone
                    del sni.mod_files[old_key]
                    touched = True
        if not touched:
            self.refresh(force=True)
            return
        self._save()
        if self.user_choices.rename_mod(old_name, new_name):
            self._save_user_choices()

    def rename_mod_file(self, old_full_name: str, new_name: str) -> None:
        """Update a single cached mod-file path after it was renamed on disk."""
        new_full = str(Path(old_full_name).parent / new_name)
        for sni in self.save_names.values():
            if old_full_name in sni.mod_files:
                sni.mod_files[new_full] = sni.mod_files[old_full_name].clone()
                del sni.mod_files[old_full_name]
                break
        self._save()


def _distinct(items: Iterable[str]) -> list[str]:
    """De-duplicate case-insensitively, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        low = item.lower()
        if low not in seen:
            seen.add(low)
            result.append(item)
    return result


def _parse_dt(value: object) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.min
    return datetime.min
