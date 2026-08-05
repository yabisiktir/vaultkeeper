"""ProfileData — the in-memory profile database and state engine.

Ported from ``ProfileData.vb`` (+ partials). Owns the four dictionaries plus the
originals, groups and change accumulator, and implements the state pipeline that
keeps mod/file states consistent.

This slice covers the **in-memory engine**: the container, accessors, the graph
operations that VB placed on ``InstalledFileData`` but which reach across the
whole profile (``reset_mod_files``, the ``Installer`` resolver, ``installer_conflicts``,
``remove_mod_file``, ``remove_file``), and the state pipeline
(``set_mod_files`` / ``update_file_states`` / ``update_mod_states`` / ``set_mod_state``).
Placing these on ProfileData is the natural Python form of VB's global-``pfd``
pattern and keeps the record classes pure data.

Deferred to the next slice: disk scanning (CreateModList/CreateFiles/rebuild),
checksum calculation over real files, and native save/load. Those need the Paths
layer and directory walking.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from functools import cmp_to_key
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.change_data import ChangeData
from vaultkeeper.core.ci_dict import CIStrDict
from vaultkeeper.core.crc import crc32_file
from vaultkeeper.core.file_data import FileData, InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.group_member import GroupMemberData
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State


class ProfileData:
    """The profile database: four dictionaries + originals, groups and changes."""

    def __init__(
        self,
        *,
        mod_installer_exists: Callable[[ModData], bool] | None = None,
    ) -> None:
        #: Every file present in the game folder tree.
        self.installed_list: dict[FileKeyInfo, InstalledFileData] = {}
        #: Every file inside every mod's ``.Mod Installer`` payload.
        self.file_list: dict[FileKeyInfo, FileData] = {}
        #: Mods and group rows, keyed case-insensitively by name.
        self.mod_list: CIStrDict[ModData] = CIStrDict()
        #: Pristine game-file CRCs, keyed by file_key (folder\\filename).
        self.original_files: CIStrDict[int] = CIStrDict()
        self.original_ee_files: CIStrDict[int] = CIStrDict()
        #: Group views, keyed by group name.
        self.groups: CIStrDict[GroupMemberData] = CIStrDict()
        #: Change accumulator.
        self.changes = ChangeData()
        #: Guards the shape of the dictionaries above.
        #:
        #: Downloads and installs run on a worker thread while the window keeps
        #: drawing the mod list from these same dicts, and Python raises
        #: "dictionary changed size during iteration" the moment a mod is created
        #: mid-listing — reproduced in under three seconds. Only *structure* needs
        #: guarding: reassigning a field on a ModData is a single bytecode and
        #: cannot tear a reader's iteration.
        #:
        #: Re-entrant because the guarded operations call each other (adding a mod
        #: seeds its group row).
        self._lock = threading.RLock()

        # Headless substitute for ModData.HasModInstaller() (a filesystem check):
        # only consulted for a mod with zero files. Defaults to "has an installer
        # identifier file". A real filesystem-backed check is injected later.
        self._mod_installer_exists = mod_installer_exists or (lambda md: md.is_installer())

    @property
    def lock(self) -> threading.RLock:
        """The profile's structural lock, for callers doing several steps at once."""
        return self._lock

    # -- Accessors --------------------------------------------------------- #
    def mod_item(self, name: str) -> ModData | None:
        return self.mod_list.get(name)

    def file_item(self, fk: FileKeyInfo) -> FileData | None:
        return self.file_list.get(fk)

    def installed_item(self, ifk: FileKeyInfo) -> InstalledFileData | None:
        return self.installed_list.get(ifk)

    def mod_exists(self, name: str) -> bool:
        return name in self.mod_list

    @property
    def mod_keys(self) -> list[str]:
        """Names of mods (excluding group rows)."""
        with self._lock:
            return [name for name, md in self.mod_list.items() if md.is_not_group_item]

    @property
    def sorted_mod_keys(self) -> list[str]:
        """Mod names in Windows-natural order."""
        from nwnfile.win_sort import win_compare

        return sorted(self.mod_keys, key=cmp_to_key(win_compare))

    @property
    def group_keys(self) -> list[str]:
        """Visible group names (hidden Installed/None groups excluded)."""
        with self._lock:
            return [
                name
                for name, md in self.mod_list.items()
                if md.is_group_item and not md.is_hidden_group
            ]

    def initialise_groups(self) -> None:
        """(Re)build the Groups views from the group rows in ModList (InitialiseGroups)."""
        self.groups = CIStrDict()
        for md in self.mod_list.values():
            if md.is_group_item:
                self.groups[md.group] = GroupMemberData(md.group, self.mod_list)

    def get_conflicts(self, file_key: str) -> list[FileKeyInfo]:
        """Mod file keys whose file_key matches (all installers of this file)."""
        with self._lock:
            target = file_key.lower()
            return [fk for fk in self.file_list if fk.file_key.lower() == target]

    def get_installer(self, file_key: str) -> str:
        """The owning-mod name for an installed file_key, or empty string."""
        ifd = self.installed_list.get(FileKeyInfo.installed_from_key(file_key))
        return ifd.installer if ifd is not None else ""

    # -- Groups ------------------------------------------------------------ #
    def ensure_mandatory_groups(self) -> None:
        """Ensure the reserved group rows (None, Installed) exist (VB AddGroups)."""
        with self._lock:
            for group in C.MANDATORY_GROUPS:
                if group not in self.mod_list:
                    self.mod_list[group] = ModData(group=group)  # a group row
            self.initialise_groups()

    def _update_mod_group(self, md: ModData, new_group: str) -> None:
        """Rewrite a mod's group and all its file keys (ModData.UpdateFileKeys)."""
        with self._lock:
            old_files = list(md.files)
            md.files.clear()
            md.group = new_group
            for fk in old_files:
                new_fk = FileKeyInfo(new_group, md.mod_name, fk.folder, fk.filename)
                fd = self.file_list.pop(fk, None)
                if fd is not None:
                    fd.key = new_fk
                    self.file_list[new_fk] = fd
                self.changes.file.removed(fk)
                self.changes.file.renamed(new_fk)
                md.files.append(new_fk)
            self.changes.mods.affected(md.mod_name)

    def move_mods_to_group(self, names: list[str], group: str) -> None:
        """Move mods into ``group`` (creating the group row if new), rewrite keys."""
        with self._lock:
            if group not in self.mod_list:
                self.mod_list[group] = ModData(group=group)  # new group row
                self.initialise_groups()
            for name in names:
                md = self.mod_item(name)
                if md is not None and md.is_not_group_item:
                    self._update_mod_group(md, group)
            self.update_file_states()
            self.update_mod_states()

    def rename_group(self, old: str, new: str) -> bool:
        """Rename a (non-reserved) group, moving its members. Returns success."""
        with self._lock:
            old_row = self.mod_list.get(old)
            if old_row is None or not old_row.is_group_item or old in C.MANDATORY_GROUPS:
                return False
            if new in self.mod_list:
                return False
            members = [
                name
                for name, md in self.mod_list.items()
                if md.is_not_group_item and md.group == old
            ]
            new_row = old_row.clone()
            new_row.group = new
            self.mod_list[new] = new_row
            self.move_mods_to_group(members, new)
            del self.mod_list[old]
            self.initialise_groups()
            return True

    # -- Mutators (ModData.Remove / RemoveAllFiles) ------------------------ #
    def remove_mod(self, name: str) -> bool:
        """Remove a mod and its installer files from the database (ModData.Remove).

        Removes the mod's FileList entries and detaches them from any installed
        files (re-resolving ownership to a remaining mod, or Unknown). Installed
        game files stay on disk — this removes the *mod definition*, not an
        uninstall. Group rows are ignored here (see :meth:`remove_group`).
        Returns True if a mod was removed.
        """
        with self._lock:
            md = self.mod_item(name)
            if md is None or md.is_group_item:
                return False

            for fk in list(md.files):
                self.changes.file.removed(fk)
                self.file_list.pop(fk, None)
                ifd = self.installed_item(fk.installed_key)
                if ifd is not None:
                    if md.is_mod_identifier_file(fk):
                        self.changes.installed.removed(ifd.key)
                        self.remove_installed_file(ifd)
                    else:
                        self.remove_mod_file(ifd, fk, True)
                self.changes.mods.affected(name)

            md.files.clear()
            del self.mod_list[name]
            self.update_file_states()
            self.update_mod_states()
            return True

    def remove_group(self, group: str) -> bool:
        """Remove a user group's row from the database (VB group ``ModData.Remove``).

        Only a non-mandatory group row can be removed, and only once it is empty —
        its member mods must be removed first (see :meth:`remove_mod`), matching VB
        ``DeleteSelectedGroups`` (which removes the group only when its count is 0).
        Returns True if a group row was removed.
        """
        with self._lock:
            row = self.mod_list.get(group)
            if row is None or row.is_not_group_item or group in C.MANDATORY_GROUPS:
                return False
            if any(
                md.is_not_group_item and md.group == group
                for md in self.mod_list.values()
            ):
                return False  # still has member mods
            del self.mod_list[group]
            self.groups.pop(group, None)
            return True

    def rename_mod(
        self,
        old_name: str,
        new_name: str,
        profile_mods_dir: Path,
        game_folders: dict[str, Path] | None = None,
    ) -> bool:
        """Rename a mod: its folder, all its file keys, and identifier files.

        Ports ModData.Rename. Renames the mod directory on disk, rewrites every
        FileList key to the new mod name, and renames identifier files
        (``<mod>.nitins/.nitres``) both in the installer and, if ``game_folders``
        is given, in the game folder. Group rows are ignored. Returns True on
        success; False if the source is missing/a group or the target name exists.
        """
        with self._lock:
            md = self.mod_item(old_name)
            if md is None or md.is_group_item or new_name in self.mod_list:
                return False

            old_dir = profile_mods_dir / old_name
            new_dir = profile_mods_dir / new_name
            if old_dir.is_dir():
                old_dir.rename(new_dir)

            new_md = md.clone()
            new_md.mod_name = new_name
            new_md.files.clear()

            for fk in md.files:
                is_identifier = md.is_mod_identifier_file(fk) and fk.filename.lower().startswith(
                    old_name.lower() + "."
                )
                new_filename = (new_name + fk.extension) if is_identifier else fk.filename
                new_fk = FileKeyInfo(fk.group, new_name, fk.folder, new_filename)

                if is_identifier:
                    base = new_dir / C.MOD_INSTALLER_DIR / fk.folder
                    old_path, new_path = base / fk.filename, base / new_filename
                    if old_path.exists():
                        old_path.rename(new_path)

                fd = self.file_list.pop(fk, None)
                if fd is not None:
                    fd.key = new_fk
                    self.file_list[new_fk] = fd
                self.changes.file.removed(fk)
                self.changes.file.renamed(new_fk)

                if is_identifier:
                    self._rename_installed_identifier(fk, new_fk, game_folders)

                new_md.files.append(new_fk)

            del self.mod_list[old_name]
            self.mod_list[new_name] = new_md
            self.changes.mods.affected(new_name)
            self.update_file_states()
            self.update_mod_states()
            return True

    def _rename_installed_identifier(
        self, fk: FileKeyInfo, new_fk: FileKeyInfo, game_folders: dict[str, Path] | None
    ) -> None:
        with self._lock:
            old_ik, new_ik = fk.installed_key, new_fk.installed_key
            ifd = self.installed_list.pop(old_ik, None)
            if ifd is None:
                return
            if game_folders is not None:
                base = game_folders.get(old_ik.folder)
                if base is not None:
                    old_path, new_path = base / old_ik.filename, base / new_ik.filename
                    if old_path.exists():
                        old_path.rename(new_path)
            ifd.key = new_ik
            self.installed_list[new_ik] = ifd
            self.changes.installed.removed(old_ik)
            self.changes.installed.renamed(new_ik)

    # -- Installation analysis (ProfileData.Properties.vb) ----------------- #
    def unknown_source_files(self, mapper) -> list[FileKeyInfo]:  # noqa: ANN001
        """Installed files from an unknown source with a mapped extension."""
        return [
            fk
            for fk, ifd in self.installed_list.items()
            if ifd.is_unknown_installer and mapper.mapped_extension(ifd.extension)
        ]

    def original_file_keys(self) -> list[FileKeyInfo]:
        """Installed files whose file_key is a known original game file."""
        with self._lock:
            return [fk for fk in self.installed_list if fk.file_key in self.original_files]

    def changed_original_files(self) -> list[FileKeyInfo]:
        """Installed original files whose CRC no longer matches the pristine value."""
        with self._lock:
            changed: list[FileKeyInfo] = []
            for fk, ifd in self.installed_list.items():
                original_crc = self.original_files.get(fk.file_key)
                if original_crc is not None and ifd.file_crc != original_crc:
                    changed.append(fk)
            return changed

    # -- Dependencies (ProfileData.vb:2840-2939) --------------------------- #
    def has_dependants(self, mod_name: str) -> bool:
        """True if any mod declares ``mod_name`` as a dependency (case-insensitive)."""
        low = mod_name.lower()
        return any(
            any(dep.lower() == low for dep in md.dependencies)
            for md in self.mod_list.values()
        )

    def validate_dependencies(self) -> int:
        """Remove dependencies pointing at non-existent mods; return the count removed."""
        removed = 0
        for md in self.mod_list.values():
            for dep in list(md.dependencies):
                if not self.mod_exists(dep):
                    md.dependencies.remove(dep)
                    removed += 1
        return removed

    def get_dependants(self) -> dict[str, list[str]]:
        """Map each required mod -> sorted list of mods that depend on it."""
        from nwnfile.win_sort import win_compare

        acc: CIStrDict[list[str]] = CIStrDict()
        for md in self.mod_list.values():
            for dep in md.dependencies:
                if dep not in acc:
                    acc[dep] = [md.mod_name]
                elif not any(x.lower() == md.mod_name.lower() for x in acc[dep]):
                    acc[dep].append(md.mod_name)
        for key in list(acc.keys()):
            acc[key].sort(key=cmp_to_key(win_compare))
        return {k: acc[k] for k in sorted(acc.keys(), key=cmp_to_key(win_compare))}

    def get_installed_dependants(self) -> dict[str, list[str]]:
        """Like :meth:`get_dependants` but limited to installed mods + installed deps."""
        acc: CIStrDict[list[str]] = CIStrDict()
        for md in self.mod_list.values():
            if not md.installed:
                continue
            for dep in md.dependencies:
                dep_mod = self.mod_item(dep)
                if dep_mod is None or not dep_mod.installed:
                    continue
                if dep not in acc:
                    acc[dep] = [md.mod_name]
                elif not any(x.lower() == md.mod_name.lower() for x in acc[dep]):
                    acc[dep].append(md.mod_name)
        return dict(acc.items())

    # -- Graph operations (VB methods on InstalledFileData, moved to pfd) --- #
    def reset_mod_files(self, ifd: InstalledFileData) -> None:
        """Rebuild ifd.mod_file_conflicts (all mods with this file_key) + mod_files
        (those whose CRC matches), sorted by FileKeyInfo.comparer."""
        with self._lock:
            target = ifd.key.file_key.lower()
            conflicts = [fk for fk in self.file_list if fk.file_key.lower() == target]
            if len(conflicts) > 1:
                conflicts.sort(key=cmp_to_key(FileKeyInfo.comparer))
            ifd.mod_file_conflicts[:] = conflicts
            ifd.mod_files[:] = [
                fk for fk in conflicts if self.file_list[fk].file_crc == ifd.file_crc
            ]

    def default_installer(self, ifd: InstalledFileData) -> None:
        """Set ifd.installer to its default classification (DefaultInstaller)."""
        original_crc = self.original_files.get(ifd.key.file_key)
        if original_crc is not None and ifd.file_crc == original_crc:
            ifd.installer = C.INSTALLER_ORIGINAL
        elif ifd.extension.lower() == ".bic":
            ifd.installer = C.INSTALLER_CHARACTER
        elif ifd.key.filename == C.LETO_LOG_FILENAME:
            ifd.installer = C.INSTALLER_LETO_LOG
        elif ifd.extension.lower() == ".txt" and ifd.key.folder.lower().endswith("vault"):
            ifd.installer = C.INSTALLER_JOURNAL_NOTES
        elif ifd.key.filename == C.NWN_LOG_FILENAME:
            ifd.installer = C.INSTALLER_NWN_LOG
        else:
            ifd.installer = C.INSTALLER_UNKNOWN

    def installer_conflicts(self, ifd: InstalledFileData) -> None:
        """Flag overridden / match-override states on the conflicting mod files."""
        for fk in ifd.mod_file_conflicts:
            fd = self.file_list[fk]
            if fd.file_crc != ifd.file_crc:
                if fd.file_state != State.OVERRIDDEN:
                    fd.file_state = State.OVERRIDDEN
                    self.changes.mods.affected(fk.mod_name)
            elif (
                fk.mod_name.lower() != ifd.installer.lower()
                and fd.file_state != State.MATCH_OVERRIDE
            ):
                fd.file_state = State.MATCH_OVERRIDE
                self.changes.mods.affected(fk.mod_name)

    def set_installer(self, ifd: InstalledFileData, value: str) -> None:
        """Resolve and set the owning mod for an installed file (Installer setter)."""
        if value != C.INSTALLER_FIND and value != "":
            ifd.installer = value
            return

        current = ifd.installer
        if ifd.is_default_installer or ifd.installer is None:
            current = ""

        if len(ifd.mod_files) == 0:
            if current != "" and self.mod_exists(ifd.installer):
                self.changes.mods.affected(current)
            self.default_installer(ifd)
            self.installer_conflicts(ifd)
            return

        if len(ifd.mod_files) == 1:
            ifd.installer = ifd.mod_files[0].mod_name
            self.file_list[ifd.mod_files[0]].file_state = State.INSTALLED
            if current != "" and current.lower() != ifd.installer.lower():
                self.changes.mods.affected(current)
            self.installer_conflicts(ifd)
            return

        # Multiple mod files: the last installed mod owns the file.
        mod_index = len(ifd.mod_files) - 1
        for i in range(mod_index, -1, -1):
            owner = self.mod_list.get(ifd.mod_files[i].mod_name)
            if owner is not None and owner.installed:
                mod_index = i
                break
        ifd.installer = ifd.mod_files[mod_index].mod_name
        self.file_list[ifd.mod_files[mod_index]].file_state = State.INSTALLED
        if current != "" and current.lower() != ifd.installer.lower():
            self.changes.mods.affected(current)
        self.installer_conflicts(ifd)

    def remove_mod_file(self, ifd: InstalledFileData, fk: FileKeyInfo, conflicts: bool) -> None:
        """Remove a mod file from an installed file; re-resolve the installer if needed."""
        if fk is None:
            return
        if conflicts and fk in ifd.mod_file_conflicts:
            ifd.mod_file_conflicts.remove(fk)
        if fk not in ifd.mod_files:
            return
        ifd.mod_files.remove(fk)
        if fk.mod_name.lower() == ifd.installer.lower():
            self.changes.mods.affected(ifd.installer)
            self.set_installer(ifd, C.INSTALLER_FIND)
            if self.mod_exists(ifd.installer):
                self.changes.mods.affected(ifd.installer)

    def remove_installed_file(self, ifd: InstalledFileData) -> None:
        """Remove an installed file entry, marking affected mods NotInstalled."""
        with self._lock:
            for fk in ifd.mod_file_conflicts:
                self.changes.mods.affected(fk.mod_name)
                fd = self.file_item(fk)
                if fd is not None:
                    fd.file_state = State.NOT_INSTALLED
            self.installed_list.pop(ifd.key, None)

    # -- State pipeline ---------------------------------------------------- #
    def set_mod_files(self, ifk: FileKeyInfo) -> None:
        """Recompute an installed file's mod files + owning installer (SetModFiles)."""
        ifd = self.installed_list.get(ifk)
        if ifd is not None:
            self.reset_mod_files(ifd)
            self.set_installer(ifd, C.INSTALLER_FIND)

    def set_mod_state(self, md: ModData) -> None:
        """Recompute a mod's state from its files (ModData.SetModState via pfd)."""
        def state_of(fk: FileKeyInfo) -> State | None:
            fd = self.file_list.get(fk)
            return fd.file_state if fd is not None else None

        md.set_mod_state(
            state_of,
            has_mod_installer=self._mod_installer_exists(md),
            total_file_count=len(self.file_list),
        )

    def update_mod_states(self) -> None:
        """Recompute states for every affected mod (UpdateModStates)."""
        for name in self.changes.mods.affected_list:
            md = self.mod_list.get(name)
            if md is not None:
                self.set_mod_state(md)

    def update_file_states(self) -> None:
        """Recompute installed/mod file states from the change lists (UpdateFileStates)."""
        with self._lock:
            processed_file_keys: set[str] = set()

            for fk in list(self.changes.installed.update_list):
                self.set_mod_files(fk)
            self.changes.installed.update_list.clear()

            # Removed mod files: re-resolve their installed counterpart.
            for fk in self.changes.file.removed_list:
                fk_low = fk.file_key.lower()
                if fk.installed_key in self.installed_list and fk_low not in processed_file_keys:
                    processed_file_keys.add(fk_low)
                    self.set_mod_files(fk.installed_key)

            # Renamed files feed into the update list.
            self.changes.file.update_list.extend(self.changes.file.renamed_list)
            for fk in list(self.changes.file.update_list):
                self.changes.mods.affected(fk.mod_name)
                fk_low = fk.file_key.lower()

                if fk.installed_key not in self.installed_list:
                    fd = self.file_list.get(fk)
                    if fd is not None:
                        fd.file_state = State.NOT_INSTALLED
                    processed_file_keys.add(fk_low)
                    continue

                if fk_low not in processed_file_keys:
                    self.set_mod_files(fk.installed_key)
                elif (
                    self.installed_list[fk.installed_key].installer.lower() != fk.mod_name.lower()
                    and self.file_list[fk].file_state != State.MATCH_OVERRIDE
                ):
                    self.file_list[fk].file_state = State.OVERRIDDEN

                processed_file_keys.add(fk_low)

            self.changes.file.update_list.clear()

    # -- Convenience for building tests / scans ---------------------------- #
    def add_mod(self, md: ModData) -> None:
        with self._lock:
            # Mods are keyed by mod name; group rows by group name (matches VB ModList).
            key = md.mod_name if md.is_not_group_item else md.group
            self.mod_list[key] = md

    def add_file(self, fd: FileData) -> None:
        with self._lock:
            self.file_list[fd.key] = fd

    def add_installed(self, ifd: InstalledFileData) -> None:
        with self._lock:
            self.installed_list[ifd.key] = ifd

    # -- Disk scan (CreateModList / CreateFiles / CreateInstalledList) ------ #
    def scan_mods(self, profile_mods_dir: Path) -> None:
        """Add every mod folder under ``profile_mods_dir`` and scan its files.

        Ports CreateModList/CreateModListThread + AddMod + AddFiles. New mods join
        the reserved GroupNone; their installer files populate FileList.
        """
        with self._lock:
            if not profile_mods_dir.is_dir():
                self.ensure_mandatory_groups()
                return
            for mod_dir in sorted(p for p in profile_mods_dir.iterdir() if p.is_dir()):
                name = mod_dir.name
                if name in self.mod_list or name in C.RESERVED_MOD_NAMES:
                    continue
                md = ModData(group=C.GROUP_NONE, mod_name=name)
                self.mod_list[name] = md
                self.changes.mods.added(name)
                self.scan_mod_files(md, profile_mods_dir)
            self.ensure_mandatory_groups()

    def scan_mod_files(self, md: ModData, profile_mods_dir: Path) -> None:
        """Populate FileList from a mod's ``.Mod Installer`` payload (AddFilesThread).

        Files are taken from sub-folders of the installer directory (matching VB,
        which enumerates sub-directories then their files); the recorded folder is
        the file's immediate parent name.
        """
        with self._lock:
            installer_dir = profile_mods_dir / md.mod_name / C.MOD_INSTALLER_DIR
            if not installer_dir.is_dir():
                return
            for path in sorted(installer_dir.rglob("*")):
                if not path.is_file() or path.parent == installer_dir:
                    continue
                fk = FileKeyInfo(md.group, md.mod_name, path.parent.name, path.name)
                if fk not in self.file_list:
                    stat = path.stat()
                    self.file_list[fk] = FileData(
                        key=fk,
                        file_state=State.UNKNOWN,
                        extension=path.suffix,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                        byte_size=stat.st_size,
                        file_crc=0,
                    )
                    md.files.append(fk)
                    self.changes.file.added(fk)

    def scan_installed(self, game_folders: dict[str, Path], root_folder_name: str) -> None:
        """Populate InstalledList from the mapped game folders (AddInstalledFilesThread).

        ``game_folders`` maps folder name -> absolute path (see
        :meth:`Mapper.nwn_folder_paths`); ``root_folder_name`` is the game root's
        directory name, used to normalise root-level files to the "nwn" marker.
        """
        with self._lock:
            for path in game_folders.values():
                if not path.is_dir():
                    continue
                for file in sorted(p for p in path.iterdir() if p.is_file()):
                    ifk = FileKeyInfo.installed(
                        file.parent.name, file.name, root_folder_name=root_folder_name
                    )
                    stat = file.stat()
                    existing = self.installed_list.get(ifk)
                    if existing is None:
                        self.installed_list[ifk] = InstalledFileData(
                            key=ifk,
                            file_state=State.INSTALLED,
                            extension=file.suffix,
                            modified=datetime.fromtimestamp(stat.st_mtime),
                            byte_size=stat.st_size,
                            file_crc=0,
                        )
                        self.changes.installed.added(ifk)
                    elif (
                        existing.byte_size != stat.st_size
                        or existing.modified != datetime.fromtimestamp(stat.st_mtime)
                    ):
                        existing.modified = datetime.fromtimestamp(stat.st_mtime)
                        existing.byte_size = stat.st_size
                        self.changes.installed.changed(ifk)

    def add_installed_file(self, ifk: FileKeyInfo, path: Path) -> None:
        """Add/update an installed-file entry from a file on disk (AddInstalledFile).

        ``ifk`` must be an installed key; ``path`` is its resolved location. No-op
        if the file does not exist. Adds the key to the Installed change list.
        """
        with self._lock:
            if not path.is_file():
                return
            self.changes.installed.added(ifk)
            stat = path.stat()
            ifd = self.installed_list.get(ifk)
            if ifd is None:
                self.installed_list[ifk] = InstalledFileData(
                    key=ifk,
                    file_state=State.INSTALLED,
                    extension=path.suffix,
                    modified=datetime.fromtimestamp(stat.st_mtime),
                    byte_size=stat.st_size,
                    file_crc=0,
                )
            else:
                ifd.byte_size = stat.st_size
                ifd.modified = datetime.fromtimestamp(stat.st_mtime)

    # -- Path resolution + checksums --------------------------------------- #
    @staticmethod
    def mod_file_path(profile_mods_dir: Path, fk: FileKeyInfo) -> Path:
        """Absolute path of a mod-installer file (FileData.FullName)."""
        rel = fk.file_key.replace("\\", "/")
        return profile_mods_dir / fk.mod_name / C.MOD_INSTALLER_DIR / rel

    @staticmethod
    def installed_file_path(game_folders: dict[str, Path], ifk: FileKeyInfo) -> Path | None:
        """Absolute path of an installed file (InstalledFileData.FullName)."""
        base = game_folders.get(ifk.folder)
        return base / ifk.filename if base is not None else None

    def calculate_checksums(
        self, profile_mods_dir: Path, game_folders: dict[str, Path]
    ) -> None:
        """Compute CRC-32 for every pending file in the change update lists.

        Mirrors CalculateChecksums headlessly (no dialog): walks
        Changes.File.UpdateList and Changes.Installed.UpdateList, computes CRCs from
        the real files, and stores them. Missing/unreadable files are left at 0.
        """
        for fk in self.changes.file.update_list:
            fd = self.file_list.get(fk)
            if fd is None:
                continue
            path = self.mod_file_path(profile_mods_dir, fk)
            fd.file_crc = _safe_crc(path)

        for ifk in self.changes.installed.update_list:
            ifd = self.installed_list.get(ifk)
            if ifd is None:
                continue
            path = self.installed_file_path(game_folders, ifk)
            ifd.file_crc = _safe_crc(path) if path is not None else 0

    def check_installed_files(
        self, game_folders: dict[str, Path], root_folder_name: str
    ) -> dict[str, int]:
        """Re-check the installed-file records against the live game (VB CheckInstalledFiles).

        Drops installed records whose file no longer exists on disk, re-scans the
        mapped game folders for added/changed files, and recomputes states. Returns
        ``{"removed", "added", "changed"}`` counts. Used by the *Validate Installed
        Data* maintenance command to re-sync after the game folder changed outside
        the tool.
        """
        with self._lock:
            removed = 0
            for ifk in list(self.installed_list):
                path = self.installed_file_path(game_folders, ifk)
                if path is None or not path.is_file():
                    ifd = self.installed_list.pop(ifk, None)
                    if ifd is not None:
                        self.changes.installed.removed(ifk)
                        removed += 1
            before_added = len(self.changes.installed.added_list)
            before_changed = len(self.changes.installed.changed_list)
            self.scan_installed(game_folders, root_folder_name=root_folder_name)
            added = len(self.changes.installed.added_list) - before_added
            changed = len(self.changes.installed.changed_list) - before_changed
            self.update_file_states()
            self.update_mod_states()
            return {"removed": removed, "added": added, "changed": changed}

    def rescan_installed_state(
        self, game_folders: dict[str, Path], root_folder_name: str
    ) -> None:
        """Recompute install state from imported mod file keys + the live game.

        This is the "rebuild from disk on first open" step for a profile imported
        from a legacy NIT Store (see :mod:`vaultkeeper.persistence.nrbf.migrate`):
        the import brings each mod's *file keys* but no FileList/InstalledList, so
        every mod would otherwise read as not-installed. Here we:

        1. reconstruct FileList from every (non-group) mod's file keys,
        2. scan the mapped game folders into InstalledList (+ CRCs),
        3. mark a mod's file installed when the game contains it — the mod-installer
           files aren't on disk to checksum, so a file that is present in the game
           adopts the installed CRC, letting the normal winner/override resolution
           (``update_file_states``/``update_mod_states``) attribute it.

        Faithful to the original's aggregate result (validated on the owner's real
        store: 2 mods fully installed, the base-game restorer campaigns partially).
        Because installer-side CRCs are unavailable, a genuine content *override*
        (installed file differs from what the mod ships) cannot be distinguished
        from a clean install — an accepted limitation of a keys-only rescan; a full
        FileList scan (with the mod folders present) resolves it precisely.
        """
        with self._lock:
            for name in list(self.mod_list):
                md = self.mod_list[name]
                if md.is_group_item:
                    continue
                for fk in md.files:
                    if fk not in self.file_list:
                        self.file_list[fk] = FileData(
                            key=fk,
                            file_state=State.UNKNOWN,
                            extension=fk.extension,
                            modified=datetime.now(),
                            byte_size=0,
                            file_crc=0,
                        )
                    self.changes.file.added(fk)
                self.changes.mods.affected(md.mod_name)

            self.scan_installed(game_folders, root_folder_name=root_folder_name)
            # No mod-installer files on disk; only the installed side gets real CRCs.
            self.calculate_checksums(Path(), game_folders)
            for fk in list(self.file_list):
                ifd = self.installed_list.get(fk.installed_key)
                if ifd is not None:
                    # A present file is this mod's file: adopt the installed CRC/size
                    # (the installer copy isn't on disk) so it matches + shows its size.
                    fd = self.file_list[fk]
                    fd.file_crc = ifd.file_crc
                    fd.byte_size = ifd.byte_size
                    fd.modified = ifd.modified

            self.update_file_states()
            self.update_mod_states()
            self.changes.reset_changes()


def _safe_crc(path: Path) -> int:
    try:
        return crc32_file(path)
    except OSError:
        return 0
