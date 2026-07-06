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

        # Headless substitute for ModData.HasModInstaller() (a filesystem check):
        # only consulted for a mod with zero files. Defaults to "has an installer
        # identifier file". A real filesystem-backed check is injected later.
        self._mod_installer_exists = mod_installer_exists or (lambda md: md.is_installer())

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
        return [name for name, md in self.mod_list.items() if md.is_not_group_item]

    @property
    def sorted_mod_keys(self) -> list[str]:
        """Mod names in Windows-natural order."""
        from vaultkeeper.core.win_sort import win_compare

        return sorted(self.mod_keys, key=cmp_to_key(win_compare))

    @property
    def group_keys(self) -> list[str]:
        """Visible group names (hidden Installed/None groups excluded)."""
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
        target = file_key.lower()
        return [fk for fk in self.file_list if fk.file_key.lower() == target]

    def get_installer(self, file_key: str) -> str:
        """The owning-mod name for an installed file_key, or empty string."""
        ifd = self.installed_list.get(FileKeyInfo.installed_from_key(file_key))
        return ifd.installer if ifd is not None else ""

    # -- Graph operations (VB methods on InstalledFileData, moved to pfd) --- #
    def reset_mod_files(self, ifd: InstalledFileData) -> None:
        """Rebuild ifd.mod_file_conflicts (all mods with this file_key) + mod_files
        (those whose CRC matches), sorted by FileKeyInfo.comparer."""
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
        # Mods are keyed by mod name; group rows by group name (matches VB ModList).
        key = md.mod_name if md.is_not_group_item else md.group
        self.mod_list[key] = md

    def add_file(self, fd: FileData) -> None:
        self.file_list[fd.key] = fd

    def add_installed(self, ifd: InstalledFileData) -> None:
        self.installed_list[ifd.key] = ifd

    # -- Disk scan (CreateModList / CreateFiles / CreateInstalledList) ------ #
    def scan_mods(self, profile_mods_dir: Path) -> None:
        """Add every mod folder under ``profile_mods_dir`` and scan its files.

        Ports CreateModList/CreateModListThread + AddMod + AddFiles. New mods join
        the reserved GroupNone; their installer files populate FileList.
        """
        if not profile_mods_dir.is_dir():
            return
        for mod_dir in sorted(p for p in profile_mods_dir.iterdir() if p.is_dir()):
            name = mod_dir.name
            if name in self.mod_list or name in C.RESERVED_MOD_NAMES:
                continue
            md = ModData(group=C.GROUP_NONE, mod_name=name)
            self.mod_list[name] = md
            self.changes.mods.added(name)
            self.scan_mod_files(md, profile_mods_dir)

    def scan_mod_files(self, md: ModData, profile_mods_dir: Path) -> None:
        """Populate FileList from a mod's ``.Mod Installer`` payload (AddFilesThread).

        Files are taken from sub-folders of the installer directory (matching VB,
        which enumerates sub-directories then their files); the recorded folder is
        the file's immediate parent name.
        """
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


def _safe_crc(path: Path) -> int:
    try:
        return crc32_file(path)
    except OSError:
        return 0
