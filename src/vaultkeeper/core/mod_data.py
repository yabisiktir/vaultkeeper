"""ModData — a mod *or* a group row in the profile database.

Ported from ``ModData.vb``. A ModData with an empty ``mod_name`` is a *group*
row; otherwise it is a *mod*. Values live in ``ProfileData.ModList`` keyed by
mod/group name.

Scope note (same layering as FileData): this holds the fields, the pure derived
properties/predicates, and ``set_mod_state`` — the state machine — ported as a
method that takes injected lookups so it is testable without a full ProfileData.
The ProfileData/filesystem-coupled behaviour (``rename``, ``remove``,
``remove_file``, ``remove_all_files``, ``create_installer``, ``update_file_keys``,
``rebuild_file_list``, path/notes resolution) lands with ProfileData; VB refs are
kept in comments.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.state import GroupStatus, Ratings, State, Weapon

#: Lookup of a file's install state by key (returns None if the key is unknown).
FileStateLookup = Callable[[FileKeyInfo], "State | None"]


@dataclass
class ModData:
    """A mod or group row. ``mod_name == ""`` denotes a group."""

    group: str
    mod_name: str = ""
    group_state: GroupStatus = GroupStatus.EXPANDED
    install_state: State = State.UNKNOWN  # declared-but-unused in VB; kept for fidelity
    mod_state: State = State.NONE
    files: list[FileKeyInfo] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    rating: Ratings = Ratings.NONE
    level_start: int = C.NULL_VALUE
    level_end: int = C.NULL_VALUE
    best_weapon: Weapon = Weapon.NONE
    hench_count: int = C.NULL_VALUE
    web_link: str = ""
    workshop_id: str = ""
    date_completed: datetime | None = None  # VB Date.MinValue -> None
    completed_count: int = 0

    def __setattr__(self, name: str, value: object) -> None:
        # VB LevelStart/LevelEnd setters coerce 0 -> NullValue ("not specified").
        if name in ("level_start", "level_end") and value == 0:
            value = C.NULL_VALUE
        super().__setattr__(name, value)

    # -- Group / identity -------------------------------------------------- #
    @property
    def is_group_item(self) -> bool:
        return self.mod_name == ""

    @property
    def is_not_group_item(self) -> bool:
        return self.mod_name != ""

    @property
    def is_hidden_group(self) -> bool:
        """True for the reserved Installed/None group rows."""
        return self.group in (C.GROUP_INSTALLED, C.GROUP_NONE)

    # -- Install state ----------------------------------------------------- #
    @property
    def installed(self) -> bool:
        """True if the mod is installed (ModState > InstallState threshold)."""
        return self.mod_state > State.INSTALL_STATE

    @property
    def is_steam_managed(self) -> bool:
        return self.workshop_id != ""

    @property
    def has_mod_file(self) -> bool:
        """True if the mod has any module file (in the modules or nwm folder)."""
        return any(fk.folder in (C.MOD_FOLDER, C.MOD_NWM_FOLDER) for fk in self.files)

    # -- File predicates (operate on self.files) --------------------------- #
    def file_key_index(self, fk: FileKeyInfo) -> int:
        """Index of ``fk`` in files (by full_key), or -1."""
        for i, existing in enumerate(self.files):
            if existing.full_key == fk.full_key:
                return i
        return -1

    def is_mod_identifier_file(self, fk: FileKeyInfo) -> bool:
        """True if ``fk`` is this mod's identifier file (in the nitconfig folder)."""
        return (
            fk.group == self.group
            and fk.mod_name == self.mod_name
            and fk.folder == C.MOD_NIT_DIR
        )

    def is_restorer(self) -> bool:
        """True if the mod carries a Restorer identifier file."""
        target = f"{C.MOD_NIT_DIR}{C.FILEKEY_SEPARATOR}{self.mod_name}{C.EXT_RESTORER}"
        return any(fk.file_key == target for fk in self.files)

    def is_installer(self) -> bool:
        """True if the mod carries a standard Installer identifier file."""
        target = f"{C.MOD_NIT_DIR}{C.FILEKEY_SEPARATOR}{self.mod_name}{C.EXT_INSTALLER}"
        return any(fk.file_key == target for fk in self.files)

    # -- State machine (SetModState) --------------------------------------- #
    def set_mod_state(
        self,
        file_state_of: FileStateLookup,
        *,
        has_mod_installer: bool,
        total_file_count: int,
    ) -> None:
        """Recompute ``mod_state`` from the mod's file states (ModData.SetModState).

        ``file_state_of`` returns a file's install state by key (None if missing);
        ``has_mod_installer`` is whether the ``.Mod Installer`` folder exists;
        ``total_file_count`` is the whole profile's FileList size (VB compares the
        override count against it — reproduced faithfully).
        """
        if not self.files:
            self.mod_state = State.NOT_INSTALLED if has_mod_installer else State.NONE
            return

        install_count = 0
        not_installed_count = 0
        override_count = 0
        match_override_count = 0

        for fk in self.files:
            state = file_state_of(fk)
            if state is None:
                # VB warns and skips (Validate Profile Data can repair later).
                continue
            if state == State.INSTALLED:
                install_count += 1
            elif state == State.NOT_INSTALLED:
                not_installed_count += 1
            elif state == State.OVERRIDDEN:
                if fk.filename in (C.PATCH_INI_FILE, C.USER_PATCH_INI_FILE):
                    # Patch ini files follow the mod's current install state.
                    if self.mod_state < State.INSTALLED:
                        not_installed_count += 1
                    else:
                        install_count += 1
                else:
                    override_count += 1
            elif state == State.MATCH_OVERRIDE:
                match_override_count += 1

        if override_count > 0:
            if not_installed_count > 0:
                self.mod_state = State.SOME_AND_OVERRIDDEN
            elif override_count < total_file_count:
                self.mod_state = State.INSTALLED_AND_OVERRIDDEN
            else:
                self.mod_state = State.OVERRIDDEN
        elif match_override_count > 0:
            if not_installed_count > 0:
                self.mod_state = State.SOME_AND_MATCH
            else:
                self.mod_state = State.MATCH_OVERRIDE
        elif install_count > 0 and not_installed_count > 0:
            self.mod_state = State.SOME_INSTALLED
        elif install_count > 0:
            self.mod_state = State.INSTALLED
        else:
            self.mod_state = State.NOT_INSTALLED

    # -- Copy -------------------------------------------------------------- #
    def clone(self) -> ModData:
        """Deep copy (mirrors ModData.Clone)."""
        md = ModData(group=self.group, mod_name=self.mod_name)
        md.best_weapon = self.best_weapon
        md.files.extend(self.files)
        md.workshop_id = self.workshop_id
        md.group_state = self.group_state
        md.hench_count = self.hench_count
        md.install_state = self.install_state
        md.level_end = self.level_end
        md.level_start = self.level_start
        md.mod_state = self.mod_state
        md.rating = self.rating
        md.web_link = self.web_link
        md.date_completed = self.date_completed
        md.completed_count = self.completed_count
        md.dependencies.extend(self.dependencies)
        return md
