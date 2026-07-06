"""ModInstallationManager — the install / uninstall / anneal engine.

Faithful headless port of ``ModInstallationManager.vb`` — the correctness heart of
NIT. UI concerns (progress dialogs, FvMods selection, status text, save timing)
are injected so the engine runs and tests headlessly:

* ``file_ops``  — the copy/delete worker (:class:`FileOps`).
* ``hak_patch`` — callable invoked to rebuild ``nwnpatch.ini`` after every op.
* ``on_save``   — callable invoked when the profile database should be persisted.
* ``anneal_mods`` on install/uninstall — the "selected mods" the auto-anneal
  considers (VB reads FvMods.SelectedIndices; the caller supplies it here).

Preserved invariants (see docs/PHASE_2.md): the <5121-byte always-copy CRC guard,
last-by-comparer winner selection, patch-ini rebuild each op, the deliberate
double ``update_profile_data`` around ``merge_saved_info``, the save/reset/restore
change-info choreography around the anneal, and EE ``.sqlite3`` companion deletes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import cmp_to_key
from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.file_ops import CopyItem, DeleteItem, FileOps
from vaultkeeper.core.mapper import EXT_EE_DATABASE, Mapper
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State

#: Always copy files smaller than this even if the CRC matches (collision guard).
NO_CRC_CHECK_REQUIRED = C.NO_CRC_CHECK_MAX_BYTES  # 5121
NO_COPIES_REQUIRED = "No file copies required."


class IOResult(StrEnum):
    NONE = "none"
    SUCCESS = "success"
    NO_SOURCE_ITEMS = "no_source_items"
    ERRORS = "errors"


@dataclass
class InstallContext:
    """Everything the engine needs to resolve real file locations."""

    profile_mods_dir: Path
    game_root: Path
    game_folders: dict[str, Path]
    root_folder_name: str
    mapper: Mapper
    is_ee: bool = True

    def mod_path(self, fk: FileKeyInfo) -> Path:
        return ProfileData.mod_file_path(self.profile_mods_dir, fk)

    def installed_path(self, ifk: FileKeyInfo) -> Path:
        base = self.game_folders.get(ifk.folder)
        if base is None:
            base = self.game_root / ifk.folder  # illegal/unmapped folder fallback
        return base / ifk.filename


class ModInstallationManager:
    """Install, uninstall and anneal mod files against the game folder."""

    def __init__(
        self,
        pd: ProfileData,
        ctx: InstallContext,
        *,
        file_ops: FileOps | None = None,
        hak_patch: Callable[[], None] = lambda: None,
        on_save: Callable[[], None] = lambda: None,
    ) -> None:
        self.pd = pd
        self.ctx = ctx
        self.file_ops = file_ops or FileOps()
        self.hak_patch = hak_patch
        self.on_save = on_save

        self.result = IOResult.NONE
        self.remove_result = IOResult.NONE
        self.result_message = ""
        self.anneal_count = 0
        self.anneal_errors = 0
        self._anneal_depth = 0

    # -- InstallFiles ------------------------------------------------------ #
    def install_files(
        self, copy_list: list[FileKeyInfo] | None, anneal_mods: list[str] | None = None
    ) -> None:
        if copy_list is None:
            return
        anneal_mods = anneal_mods or []
        pd = self.pd

        mods_installed: dict[str, int] = {}
        build: list[FileKeyInfo] = []
        seen_targets: set[Path] = set()

        def file_list_add(fk: FileKeyInfo) -> None:
            target = self.ctx.installed_path(fk.installed_key)
            if target not in seen_targets:
                seen_targets.add(target)
                build.append(fk)

        def add_to_file_list(fk: FileKeyInfo, ifd) -> None:
            fd = pd.file_item(fk)
            if fd.file_crc != ifd.file_crc or ifd.byte_size < NO_CRC_CHECK_REQUIRED:
                file_list_add(fk)
            else:
                pd.changes.installed.added(ifd.key)
                mods_installed[fk.mod_name] = mods_installed.get(fk.mod_name, 0) + 1

        for fk in copy_list:
            ifd = pd.installed_item(fk.installed_key)
            mods_installed.setdefault(fk.mod_name, 0)
            if ifd is None:
                file_list_add(fk)
            elif ifd.mod_file_conflicts:
                for mfk in ifd.mod_file_conflicts:
                    pd.changes.mods.affected(mfk.mod_name)
                conflicts = [
                    mfk
                    for mfk in ifd.mod_file_conflicts
                    if (pd.mod_item(mfk.mod_name) and pd.mod_item(mfk.mod_name).installed)
                    or mfk.full_key == fk.full_key
                ]
                if len(conflicts) > 1 and conflicts.index(fk) < len(conflicts) - 1:
                    mods_installed[fk.mod_name] += 1  # overridden by a later winner
                    continue
                add_to_file_list(fk, ifd)
            else:
                add_to_file_list(fk, ifd)

        if not build:
            self.hak_patch()
            self._update_profile_data()
            self.result = IOResult.NO_SOURCE_ITEMS
            self.result_message = NO_COPIES_REQUIRED
            return

        pd.changes.save_info()
        pd.changes.reset_changes()

        items = [
            CopyItem(
                source=self.ctx.mod_path(fk),
                target=self.ctx.installed_path(fk.installed_key),
                key=fk,
                crc=pd.file_item(fk).file_crc,
            )
            for fk in build
        ]
        results = self.file_ops.copy(items)
        success = 0
        for r in results:
            if r.success:
                ifk = r.key.installed_key
                pd.add_installed_file(ifk, self.ctx.installed_path(ifk))
                installed = pd.installed_item(ifk)
                if installed is not None:
                    installed.file_crc = pd.file_item(r.key).file_crc
                mods_installed[r.key.mod_name] = mods_installed.get(r.key.mod_name, 0) + 1
                success += 1
        no_errors = success == len(results)
        self.result = IOResult.SUCCESS if no_errors else IOResult.ERRORS
        self.result_message = f"Files installed: {success}"

        # Set mod install state before the file-state update (so match-override
        # files attach to the right installer).
        for name, count in mods_installed.items():
            mdi = pd.mod_item(name)
            if mdi is not None and (len(mdi.files) == count or no_errors):
                mdi.mod_state = State.INSTALLED

        self.hak_patch()
        self._update_profile_data()
        # Double update: merge saved change info and update again (required for the
        # install -> uninstall -> install sequence).
        pd.changes.merge_saved_info()
        self._update_profile_data()

        result_text = self.result_message
        pd.changes.save_info()
        pd.changes.reset_changes()
        self.anneal(anneal_mods)
        pd.changes.restore_saved_info()
        self.result_message = result_text

    # -- UninstallFiles ---------------------------------------------------- #
    def uninstall_files(
        self, remove_list: list[FileKeyInfo] | None, anneal_mods: list[str] | None = None
    ) -> None:
        if remove_list is None:
            return
        anneal_mods = anneal_mods or []
        pd = self.pd

        deletes: list[FileKeyInfo] = []  # installed keys to delete
        seen_targets: set[Path] = set()
        copy_list: list[FileKeyInfo] = []
        sql_files: list[str] = []

        def delete_add(ifk: FileKeyInfo) -> None:
            target = self.ctx.installed_path(ifk)
            if target not in seen_targets:
                seen_targets.add(target)
                deletes.append(ifk)

        for fk in remove_list:
            md = pd.mod_item(fk.mod_name)
            if md is not None and md.installed:
                md.mod_state = State.NOT_INSTALLED

            ifd = pd.installed_item(fk.installed_key)
            if ifd is None:
                if md is not None:
                    md.mod_state = State.NOT_INSTALLED
                continue

            if fk.filename in (C.PATCH_INI_FILE, C.USER_PATCH_INI_FILE):
                fd = pd.file_item(fk)
                if fd is not None:
                    fd.file_state = State.OVERRIDDEN
                continue

            if ifd.mod_file_conflicts:
                for cfk in ifd.mod_file_conflicts:
                    pd.changes.mods.affected(cfk.mod_name)

            # EE: also delete the companion .sqlite3 of a database-extension file.
            if (
                self.ctx.is_ee
                and ifd.extension.lower() != EXT_EE_DATABASE
                and self.ctx.mapper.is_database_extension(ifd.extension)
            ):
                fname = Path(ifd.key.filename).stem
                if fname not in sql_files:
                    sql_files.append(fname)
                    fki = FileKeyInfo.installed(ifd.key.folder, f"{fname}{EXT_EE_DATABASE}")
                    if pd.installed_item(fki) is not None:
                        delete_add(fki)

            if len(ifd.mod_file_conflicts) < 2:
                delete_add(ifd.key)
                continue

            candidates = [
                cfk
                for cfk in ifd.mod_file_conflicts
                if cfk.full_key != fk.full_key
                and pd.mod_item(cfk.mod_name)
                and pd.mod_item(cfk.mod_name).installed
                and cfk not in remove_list
            ]
            if not candidates:
                delete_add(ifd.key)
                continue

            if len(candidates) > 1:
                candidates.sort(key=cmp_to_key(FileKeyInfo.comparer))
                candidates.reverse()
            mfk = candidates[0]

            mfk_fd = pd.file_item(mfk)
            if mfk_fd.file_state == State.MATCH_OVERRIDE and ifd.byte_size >= NO_CRC_CHECK_REQUIRED:
                pd.changes.installed.changed(mfk.installed_key)
            elif mfk_fd.file_crc != ifd.file_crc or ifd.byte_size < NO_CRC_CHECK_REQUIRED:
                copy_list.append(mfk)

        # Never copy something that is being deleted.
        copy_list = [fk for fk in copy_list if fk not in remove_list]

        delete_items = [DeleteItem(self.ctx.installed_path(ifk), ifk) for ifk in deletes]
        results = self.file_ops.delete(delete_items)
        success = 0
        for r in results:
            if r.success:
                ifd = pd.installed_item(r.key)
                if ifd is not None:
                    pd.changes.installed.removed(ifd.key)
                    pd.remove_installed_file(ifd)
                success += 1
        self.remove_result = IOResult.SUCCESS if success == len(results) else IOResult.ERRORS
        remove_message = f"Files uninstalled: {success}"

        # Remove the entries from the database.
        for fk in remove_list:
            ifd = pd.installed_item(fk.installed_key)
            if ifd is not None:
                pd.remove_mod_file(ifd, fk, False)
                if len(ifd.mod_files) == 0:
                    pd.changes.installed.removed(ifd.key)
                    pd.remove_installed_file(ifd)

        if copy_list:
            # Anneal-install the replacement winners.
            self.install_files(copy_list, anneal_mods)
            self.result_message = (
                f"{remove_message} {self.result_message.replace('Files installed', 'Annealed')}"
            )
        else:
            self.hak_patch()
            self.result = self.remove_result
            self.result_message = remove_message
            self._update_profile_data()

    # -- Anneal ------------------------------------------------------------ #
    def anneal(self, mod_list: list[str] | None) -> None:
        if mod_list is None:
            return
        pd = self.pd
        copy_list: list[FileKeyInfo] = []
        error_count = 0

        for modname in mod_list:
            mdi = pd.mod_item(modname)
            if mdi is None or len(mdi.files) == 0:
                continue
            for fk in mdi.files:
                ifd = pd.installed_item(fk.installed_key)
                if ifd is None or ifd.is_default_installer or not ifd.mod_file_conflicts:
                    continue

                # Repair any null conflict entries (legacy crash guard).
                valid = [mfk for mfk in ifd.mod_file_conflicts if mfk is not None]
                if len(valid) != len(ifd.mod_file_conflicts):
                    error_count += 1
                    ifd.mod_file_conflicts[:] = valid

                conflicts = [
                    mfk
                    for mfk in valid
                    if pd.mod_item(mfk.mod_name) and pd.mod_item(mfk.mod_name).installed
                ]
                if not conflicts:
                    continue

                fk_index = _index_of(conflicts, fk) + 1
                if fk_index == len(conflicts):
                    if ifd.installer.lower() != modname.lower():
                        copy_list.append(fk)
                elif ifd.installer.lower() != conflicts[-1].mod_name.lower():
                    copy_list.append(conflicts[-1])

        self.anneal_errors = error_count
        copy_list = list(dict.fromkeys(copy_list))  # Distinct, order-preserving
        self.anneal_count = len(copy_list)
        if self.anneal_count > 0 and self._anneal_depth < 8:
            self._anneal_depth += 1
            try:
                self.install_files(copy_list, mod_list)
            finally:
                self._anneal_depth -= 1
            self.result_message = self.result_message.replace("installed", "annealed")
        elif self.anneal_count == 0:
            self.result_message = ""

    # -- Internal ---------------------------------------------------------- #
    def _update_profile_data(self) -> None:
        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.on_save()


def _index_of(items: list[FileKeyInfo], target: FileKeyInfo) -> int:
    for i, item in enumerate(items):
        if item == target:
            return i
    return -1
