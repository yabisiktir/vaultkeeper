"""ProfileController — the bridge between the UI and the domain engine.

Holds the active :class:`ProfileData`, the install :class:`ModInstallationManager`
and the store location, and exposes high-level operations the UI calls (list
mods by group, install/uninstall selected mods, save). Keeping this UI-free makes
the whole app flow testable without Qt.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vaultkeeper.app_paths import config_root
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.hak_patch import HakPatchManager
from vaultkeeper.core.install_manager import InstallContext, ModInstallationManager
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.game.config_guard import ConfigChange, ConfigGuard
from vaultkeeper.game.locations import HostOS, user_documents_dir
from vaultkeeper.game.nwn_folders import read_alias_locations
from vaultkeeper.persistence.profile_store import load_profile, save_profile
from vaultkeeper.ui.play_loop import PlayLoop


def _has_unscanned_mods(pd: ProfileData) -> bool:
    """True if the profile has mods with file keys but no scanned FileList.

    Signature of a legacy import (ModData only) that needs its install state
    rebuilt from disk on first open.
    """
    return any(
        (md := pd.mod_item(name)) is not None and bool(md.files)
        for name in pd.mod_keys
    )


class ProfileController:
    """Owns the active profile and drives install/uninstall/save."""

    def __init__(
        self,
        pd: ProfileData,
        ctx: InstallContext,
        *,
        store_path: Path | None = None,
        settings_path: Path | None = None,
    ) -> None:
        self.pd = pd
        self.ctx = ctx
        self.store_path = store_path
        #: Settings file for persisting non-profile prefs (map overrides); None =
        #: the platform default location.
        self._settings_path = settings_path
        patch_ini = ctx.game_root / "nwnpatch.ini"
        self._hpm = HakPatchManager(pd, patch_ini)
        self.engine = ModInstallationManager(
            pd, ctx, hak_patch=self._hpm.create_nwn_patch_ini_file, on_save=self.save
        )
        self._play_loop: PlayLoop | None = None
        #: Optional GameMapper prompter (the app injects a Qt-backed one).
        self.play_prompter = None
        #: HTTP client for Vault operations (tests inject a FakeHttpClient).
        self._http = None
        #: Archive backend for publish/extract (tests inject a FakeArchiveExtractor).
        self._extractor = None
        #: BIK→WBM converter (tests inject a FakeBikConverter).
        self._bik_backend = None

    # -- Construction ------------------------------------------------------ #
    @classmethod
    def open_profile(
        cls,
        *,
        profile_mods_dir: Path,
        game_root: Path,
        store_path: Path | None = None,
        is_ee: bool = True,
        map_overrides: dict[str, dict[str, str]] | None = None,
        map_exclude_overrides: dict[str, list[str]] | None = None,
        settings_path: Path | None = None,
        game_user_dir: Path | None = None,
    ) -> ProfileController:
        """Load a profile from ``store_path`` (or scan from disk if absent), wire it up.

        ``game_user_dir`` overrides the auto-resolved game user-data folder (the
        Settings *Locations* page lets the user set it); ``None`` = auto-resolve.
        """
        mapper = Mapper(
            is_ee=is_ee,
            overrides=map_overrides,
            exclude_overrides=map_exclude_overrides,
        )
        # The EE user-dir folder split only applies when the caller knows the real
        # NWN user-files folder (the app passes settings.game_user_path). Without it
        # we keep the standard single-root layout, so scans/installs stay inside the
        # given game_root (tests, and fresh setups before Locations is configured).
        folder_user_dir = game_user_dir
        if game_user_dir is None:
            game_user_dir = user_documents_dir(HostOS.current())
        game_folders = mapper.nwn_folder_paths(
            game_root,
            user_dir=folder_user_dir,
            alias_locations=(
                read_alias_locations(folder_user_dir) if folder_user_dir else None
            ),
        )

        pd = load_profile(store_path) if store_path else None
        if pd is None:
            pd = ProfileData()
            pd.scan_mods(profile_mods_dir)
            pd.scan_installed(game_folders, root_folder_name=game_root.name)
            pd.calculate_checksums(profile_mods_dir, game_folders)
            pd.update_file_states()
            pd.update_mod_states()
            pd.changes.reset_changes()
            pd.initialise_groups()
        elif not pd.file_list and _has_unscanned_mods(pd):
            # A profile imported from a legacy NIT Store carries mod definitions +
            # file keys but no FileList/InstalledList — rebuild install state from
            # the live game so already-installed mods show correctly (first open).
            pd.rescan_installed_state(game_folders, root_folder_name=game_root.name)

        ctx = InstallContext(
            profile_mods_dir=profile_mods_dir,
            game_root=game_root,
            game_folders=game_folders,
            root_folder_name=game_root.name,
            mapper=mapper,
            is_ee=is_ee,
            game_user_dir=game_user_dir,
        )
        return cls(pd, ctx, store_path=store_path, settings_path=settings_path)

    # -- Queries ----------------------------------------------------------- #
    def groups(self) -> list[tuple[str, list[ModData]]]:
        """Return (group_name, member mods) pairs, groups and members natural-sorted."""
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare

        by_group: dict[str, list[ModData]] = {}
        # Seed every existing (visible) group so empty groups still render as
        # drag-drop targets — VB ApplyGroupsAndStatus (NIT.ModView.vb) adds a
        # header for every pd.Groups row before placing any mods.
        for gname in self.pd.group_keys:
            by_group.setdefault(gname, [])
        for name in self.pd.mod_keys:
            md = self.pd.mod_item(name)
            if md is not None:
                by_group.setdefault(md.group, []).append(md)
        def by_name(a: ModData, b: ModData) -> int:
            return win_compare(a.mod_name, b.mod_name)

        result = []
        for group in sorted(by_group, key=cmp_to_key(win_compare)):
            members = sorted(by_group[group], key=cmp_to_key(by_name))
            result.append((group, members))
        return result

    def mod_files(self, names: list[str]) -> list[FileKeyInfo]:
        keys: list[FileKeyInfo] = []
        for name in names:
            md = self.pd.mod_item(name)
            if md is not None:
                keys.extend(md.files)
        return keys

    def mod_contents_report(self, mod_name: str) -> dict:
        """The selected mod's files grouped by folder, with per-file install state.

        Feeds the Contents pane (VB FvContents): each file carries its install
        state (from FileList) and size so the pane can icon/colour it like the mod
        list. Folders and files are Windows natural-sorted.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.state import State
        from vaultkeeper.core.win_sort import win_compare

        md = self.pd.mod_item(mod_name)
        by_folder: dict[str, list[dict]] = {}
        if md is not None:
            for fk in md.files:
                fd = self.pd.file_list.get(fk)
                state = fd.file_state if fd is not None else State.UNKNOWN
                size = fd.byte_size if fd is not None else 0
                by_folder.setdefault(fk.folder, []).append(
                    {
                        "name": fk.filename,
                        "state": state,
                        "size": size,
                        "size_text": _fmt_size(size),
                    }
                )
        folders = []
        installed = 0
        def by_name(a: dict, b: dict) -> int:
            return win_compare(a["name"], b["name"])

        for folder in sorted(by_folder, key=cmp_to_key(win_compare)):
            files = sorted(by_folder[folder], key=cmp_to_key(by_name))
            installed += sum(1 for f in files if f["state"] > State.NOT_INSTALLED)
            folders.append({"folder": folder, "files": files})
        total = sum(len(f["files"]) for f in folders)
        return {"folders": folders, "count": total, "installed": installed}

    def find_profile_files(
        self,
        query: str,
        *,
        match_case: bool = False,
        whole_word: bool = False,
    ) -> dict:
        """Search every mod's installer files by name (VB ``FindProfileFilesDialogue``).

        Filters the profile's file list by a substring (optionally case-sensitive /
        whole-word) match on the file name, excluding the game's installed-files
        pseudo-mod. An empty query returns no rows (VB behaviour). Rows carry the
        owning ``mod`` / ``filename`` / ``folder``, Windows-sorted by mod then file.
        Returns ``{"rows", "count"}``.
        """
        import re
        from functools import cmp_to_key

        from vaultkeeper.core import constants as C
        from vaultkeeper.core.win_sort import win_compare

        rows: list[dict] = []
        if query:
            needle = query if match_case else query.lower()
            word_re = (
                re.compile(rf"\b{re.escape(needle)}\b") if whole_word else None
            )
            for fk in self.pd.file_list:
                if fk.mod_name == C.INSTALLED_FILES_LABEL:
                    continue  # skip the game's installed files
                hay = fk.filename if match_case else fk.filename.lower()
                if word_re is not None:
                    if word_re.search(hay) is None:
                        continue
                elif needle not in hay:
                    continue
                rows.append(
                    {"mod": fk.mod_name, "filename": fk.filename, "folder": fk.folder}
                )

        rows.sort(
            key=cmp_to_key(
                lambda a, b: win_compare(a["mod"], b["mod"])
                or win_compare(a["filename"], b["filename"])
            )
        )
        return {"rows": rows, "count": len(rows)}

    def mod_file_path(self, mod_name: str, folder: str, filename: str) -> Path | None:
        """The absolute path of one of a mod's installer files, or ``None``.

        The Contents pane files live under ``<mod>/.Mod Installer/<folder>/<file>``
        (VB ``FvContents`` file paths); returns the path when it exists on disk.
        """
        from vaultkeeper.core import constants as C

        md = self.pd.mod_item(mod_name)
        if md is None:
            return None
        path = (
            self.ctx.profile_mods_dir / mod_name / C.MOD_INSTALLER_DIR / folder / filename
        )
        return path if path.is_file() else None

    def copy_mod_file(
        self,
        src_mod: str,
        folder: str,
        filename: str,
        dest_mod: str,
        *,
        move: bool = False,
    ) -> bool:
        """Copy (or move) one installer file between mods (VB CmContents Copy/Cut+Paste).

        The file is placed in ``dest_mod``'s ``.Mod Installer`` under the same folder,
        and the destination's file list is rescanned. With ``move`` the source file is
        deleted afterward (Cut+Paste). Returns True on success; a no-op paste onto the
        same file is rejected.
        """
        import shutil

        from vaultkeeper.core import constants as C

        src = self.mod_file_path(src_mod, folder, filename)
        dest_md = self.pd.mod_item(dest_mod)
        if src is None or dest_md is None or dest_md.is_group_item:
            return False
        dest = (
            self.ctx.profile_mods_dir / dest_mod / C.MOD_INSTALLER_DIR / folder / filename
        )
        if src.resolve() == dest.resolve():
            return False  # pasting a file onto itself
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        self.pd.scan_mod_files(dest_md, self.ctx.profile_mods_dir)
        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.save()
        if move:
            self.delete_mod_file(src_mod, folder, filename)
        return True

    def delete_mod_file(self, mod_name: str, folder: str, filename: str) -> bool:
        """Delete one installer file from a mod (VB ``CmContents`` Delete).

        Removes the file from the mod's ``.Mod Installer`` payload, drops its FileKey
        from the database and recomputes states (the same safe path as Remove ERF
        Files). Returns True when a file was removed.
        """
        target_folder = folder.lower()
        target_name = filename.lower()
        removed = self._remove_mod_files(
            mod_name,
            lambda fk: fk.folder.lower() == target_folder
            and fk.filename.lower() == target_name,
        )
        return removed > 0

    def mod_web_link(self, mod_name: str) -> str:
        """A mod's Neverwinter Vault / web page address (VB ``ModData.WebLink``)."""
        md = self.pd.mod_item(mod_name)
        return md.web_link if md is not None else ""

    def set_mod_web_link(self, mod_name: str, url: str) -> dict:
        """Set (or clear) a mod's web page address (VB ``MsEditWebLink``).

        An empty string clears the link (VB "Clear the current link to remove the
        address."); a non-empty value must be a valid URL (VB ``ValidateLink`` →
        ``IsUrl``). Persists on success. Returns ``{"ok", "message"}``.
        """
        from vaultkeeper.core.urls import is_url

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {"ok": False, "message": f"Unknown mod: {mod_name}"}
        url = url.strip()
        if url and not is_url(url):
            return {
                "ok": False,
                "message": "You have not specified a valid web page address (URL).",
            }
        md.web_link = url
        self.save()
        message = f"Web link {'set' if url else 'cleared'} for {mod_name}."
        return {"ok": True, "message": message}

    def mod_properties(self, mod_name: str) -> dict | None:
        """Current editable metadata for a mod (VB TlModProperties), or None."""
        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return None
        return {
            "rating": md.rating,
            "best_weapon": md.best_weapon,
            "level_start": md.level_start,
            "level_end": md.level_end,
            "hench_count": md.hench_count,
        }

    def set_mod_properties(
        self,
        mod_name: str,
        *,
        rating=None,
        best_weapon=None,
        level_start: int | None = None,
        level_end: int | None = None,
        hench_count: int | None = None,
    ) -> bool:
        """Update a mod's editable metadata (Rating/Weapon/Levels/Henchmen); persist.

        Only the supplied fields change. ``level_start``/``level_end`` coerce 0 to the
        "not specified" sentinel via ``ModData`` (VB TxLevel behaviour).
        """
        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return False
        if rating is not None:
            md.rating = rating
        if best_weapon is not None:
            md.best_weapon = best_weapon
        if level_start is not None:
            md.level_start = level_start
        if level_end is not None:
            md.level_end = level_end
        if hench_count is not None:
            md.hench_count = hench_count
        self.save()
        return True

    # -- Operations -------------------------------------------------------- #
    def install(self, names: list[str]) -> str:
        self.engine.install_files(self.mod_files(names), anneal_mods=names)
        return self.engine.result_message

    def _settings(self):
        """Load the current settings (VB My.Settings)."""
        from vaultkeeper.config.settings import load_settings

        return load_settings(self._settings_path)

    def uninstall(self, names: list[str]) -> str:
        names = list(names)
        if self._settings().uninstall_dependencies:
            names = self._with_removable_dependencies(names)
        self.engine.uninstall_files(self.mod_files(names), anneal_mods=names)
        return self.engine.result_message

    def _with_removable_dependencies(self, names: list[str]) -> list[str]:
        """Extend ``names`` with each mod's installed dependencies that no *other*
        installed mod still needs (VB BehaviourUninstallDependencies cascade)."""
        removing = {n.lower() for n in names}
        dependants = self.pd.get_installed_dependants()  # dep -> [installed dependants]
        result = list(names)
        queue = list(names)
        while queue:
            md = self.pd.mod_item(queue.pop())
            if md is None:
                continue
            for dep in md.dependencies:
                if dep.lower() in removing:
                    continue
                dep_mod = self.pd.mod_item(dep)
                if dep_mod is None or not dep_mod.installed:
                    continue
                # Only remove the dependency if every installed mod that needs it is
                # itself being removed.
                if all(d.lower() in removing for d in dependants.get(dep, [])):
                    removing.add(dep.lower())
                    result.append(dep_mod.mod_name)
                    queue.append(dep_mod.mod_name)
        return result

    def remove_mods(self, names: list[str]) -> int:
        """Remove mod definitions from the profile; return how many were removed."""
        removed = sum(1 for name in names if self.pd.remove_mod(name))
        self.save()
        return removed

    def rename_mod(self, old_name: str, new_name: str) -> bool:
        """Rename a mod (folder + keys + identifier files); persist on success."""
        ok = self.pd.rename_mod(
            old_name, new_name, self.ctx.profile_mods_dir, self.ctx.game_folders
        )
        if ok:
            self.save()
        return ok

    # -- Mod creation ------------------------------------------------------ #
    def create_mod(self, name: str, group: str | None = None) -> bool:
        """Create a new mod folder + database row (VB New Mod). False if it exists."""
        from vaultkeeper.core import constants as C

        if not name or name in self.pd.mod_list:
            return False
        if group is None:
            from vaultkeeper.config.settings import load_settings

            group = load_settings(self._settings_path).default_group or None
        group = group or C.GROUP_NONE
        (self.ctx.profile_mods_dir / name / C.MOD_INSTALLER_DIR).mkdir(
            parents=True, exist_ok=True
        )
        self.pd.add_mod(ModData(group=group, mod_name=name))
        self.pd.initialise_groups()
        self.save()
        return True

    def _remove_mod_files(self, mod_name: str, matches) -> int:  # noqa: ANN001
        """Delete a mod's installer files matching ``matches(fk)``; rescan states."""
        from vaultkeeper.core import constants as C

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return 0
        installer = self.ctx.profile_mods_dir / mod_name / C.MOD_INSTALLER_DIR
        removed = 0
        for fk in list(md.files):
            if matches(fk):
                (installer / fk.folder / fk.filename).unlink(missing_ok=True)
                self.pd.file_list.pop(fk, None)
                if fk in md.files:
                    md.files.remove(fk)
                self.pd.changes.file.removed(fk)
                removed += 1
        if removed:
            self.pd.update_file_states()
            self.pd.update_mod_states()
            self.save()
        return removed

    def remove_erf_files(self, mod_name: str) -> int:
        """Remove leftover ``.erf`` archives from a mod's installer (VB Remove ERFs)."""
        from vaultkeeper.core import constants as C

        return self._remove_mod_files(
            mod_name, lambda fk: fk.filename.lower().endswith(C.EXT_ERF)
        )

    def remove_leto_log_files(self, mod_name: str) -> int:
        """Remove Leto log files from a mod's installer (VB Remove Leto Log Files)."""
        from vaultkeeper.core import constants as C

        target = C.LETO_LOG_FILENAME.lower()
        return self._remove_mod_files(
            mod_name, lambda fk: fk.filename.lower() == target
        )

    def remove_all_leto_log_files(self, *, to_trash: bool = True) -> int:
        """Sweep every managed mod's installer AND each installed game folder for
        Leto log files, removing them (VB ``Workers.RemoveLetoLogFiles``).

        This is the global sweep behind both the auto-cleanup run on startup (when
        ``Settings.delete_leto_logs`` is on — VB ``DeleteLetoLogs``) and the manual
        **Remove Leto Log Files** command (VB ``MsRemoveLetoLogFiles_Click`` runs the
        same worker). Game-folder copies go to the recycle bin (VB
        ``SendToRecycleBin``); delete failures are tolerated and skipped (VB
        ``letoFailures``). Installer-payload copies inside the managed store are
        removed like the other installer cleanups (permanent — they are regenerable).
        Returns the total number of Leto log files removed.
        """
        from vaultkeeper.core import constants as C
        from vaultkeeper.core import fs

        target = C.LETO_LOG_FILENAME.lower()
        removed = 0
        # 1) Managed profile mod installers (VB loop over Paths.ProfileMods).
        for name in list(self.pd.mod_keys):
            md = self.pd.mod_item(name)
            if md is None or md.is_group_item:
                continue
            installer = self.ctx.profile_mods_dir / name / C.MOD_INSTALLER_DIR
            for fk in list(md.files):
                if fk.filename.lower() == target:
                    (installer / fk.folder / fk.filename).unlink(missing_ok=True)
                    self.pd.file_list.pop(fk, None)
                    if fk in md.files:
                        md.files.remove(fk)
                    self.pd.changes.file.removed(fk)
                    removed += 1
        # 2) Installed game folders (VB loop over Mapper.NwnFolders).
        seen: set[Path] = set()
        for folder in self.ctx.game_folders.values():
            log_path = folder / C.LETO_LOG_FILENAME
            if log_path in seen or not log_path.is_file():
                continue
            seen.add(log_path)
            try:
                fs.delete(log_path, to_trash=to_trash)
            except Exception:  # noqa: BLE001 — VB tolerates delete failures and moves on
                continue
            removed += 1
        if removed:
            self.pd.update_file_states()
            self.pd.update_mod_states()
            self.save()
        return removed

    def remove_illegal_mod_files(self) -> dict:
        """Relocate every mod file that maps to no legal folder / non-NWN extension.

        Faithful port of ``ProfileData.RemoveIllegalModFiles``: a mod-installer file
        is *illegal* when its folder is not a mapped NWN folder
        (``not is_legal_folder``) or its extension is not an NWN extension
        (``not is_nwn_extension``). Illegal whole folders are moved to the mod's
        ``.Removed Items`` area (VB ``ModInstallerIllegal``); extension-illegal files
        sitting in an otherwise-legal folder are moved individually. All illegal file
        keys are dropped from the database, then states are recomputed and persisted.
        Returns ``{"folders", "files", "message"}`` (VB status counts).
        """
        import shutil

        from vaultkeeper.core import constants as C
        from vaultkeeper.core import fs

        mapper = self.ctx.mapper
        illegal = [
            fk
            for fk in list(self.pd.file_list)
            if not mapper.is_legal_folder(fk.folder)
            or not mapper.is_nwn_extension(fk.extension)
        ]
        if not illegal:
            return {"folders": 0, "files": 0, "message": "Illegal Mod items removed: None."}

        # Distinct (mod, folder) pairs whose folder itself is illegal.
        illegal_folders: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for fk in illegal:
            if not mapper.is_legal_folder(fk.folder):
                key = (fk.mod_name.lower(), fk.folder.lower())
                if key not in seen:
                    seen.add(key)
                    illegal_folders.append((fk.mod_name, fk.folder))
        illegal_folder_set = {(m.lower(), f.lower()) for m, f in illegal_folders}

        # Files illegal only by extension (their folder is legal) move individually.
        illegal_files = [
            fk
            for fk in illegal
            if (fk.mod_name.lower(), fk.folder.lower()) not in illegal_folder_set
        ]

        for mod_name, folder in illegal_folders:
            src = self.ctx.profile_mods_dir / mod_name / C.MOD_INSTALLER_DIR / folder
            if src.is_dir():
                dest = self.ctx.profile_mods_dir / mod_name / C.REMOVED_ITEMS_DIR / folder
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.move(str(src), str(dest))

        for fk in illegal_files:
            src = (
                self.ctx.profile_mods_dir
                / fk.mod_name
                / C.MOD_INSTALLER_DIR
                / fk.folder
                / fk.filename
            )
            if src.is_file():
                dest = (
                    self.ctx.profile_mods_dir
                    / fk.mod_name
                    / C.REMOVED_ITEMS_DIR
                    / fk.folder
                    / fk.filename
                )
                fs.move_file(src, dest, overwrite=True)

        for fk in illegal:
            md = self.pd.mod_item(fk.mod_name)
            self.pd.file_list.pop(fk, None)
            if md is not None and fk in md.files:
                md.files.remove(fk)
            self.pd.changes.file.removed(fk)

        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.save()
        folders_n = len(illegal_folders)
        files_n = len(illegal_files)
        return {
            "folders": folders_n,
            "files": files_n,
            "message": (
                f"Illegal Mod items removed. Folders: {folders_n or 'None'}. "
                f"Files: {files_n or 'None'}."
            ),
        }

    def add_files_to_mod(self, mod_name: str, file_paths: list[Path]) -> int:
        """Copy files into a mod's ``.Mod Installer``, each in its mapped game folder.

        Ports VB Add Files: each source file is placed under the folder the Mapper
        assigns for it (``hak``/``override``/``tlk``/…), then the mod's file list is
        rescanned. Returns the number of files added.
        """
        import shutil

        from vaultkeeper.core import constants as C

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return 0
        installer = self.ctx.profile_mods_dir / mod_name / C.MOD_INSTALLER_DIR
        added = 0
        for source in file_paths:
            source = Path(source)
            if not source.is_file():
                continue
            folder = self.ctx.mapper.get_mapped_folder(source.name)
            dest = installer / folder / source.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            added += 1
        if added:
            self.pd.scan_mod_files(md, self.ctx.profile_mods_dir)
            self.pd.update_file_states()
            self.pd.update_mod_states()
            self.save()
        return added

    def add_mods_from_files(self, paths: list[Path], group: str | None = None) -> dict:
        """Create a new mod from each archive, extracting its files (VB MsAddMods/ModPaste).

        For each selected archive a mod folder named after the archive is created
        under ``group`` (the currently-selected group, else No Group), the archive is
        extracted into it and a ``_Downloads`` folder is added — leaving the mod ready
        for Create Installer, exactly as the VB "Add Mods from Files" flow does. A file
        that 7-Zip can't extract, or whose mod name already exists, is skipped. Returns
        ``{"created", "ignored", "errors", "message"}``.
        """
        import shutil

        from vaultkeeper.core import constants as C
        from vaultkeeper.core.archive import is_extractable

        if group is None:
            s = self._settings()
            if s.move_added_mods and s.default_group:
                group = s.default_group
        group = group or C.GROUP_NONE
        created: list[str] = []
        ignored: list[str] = []
        errors: list[str] = []
        for raw in paths:
            source = Path(raw)
            if not is_extractable(source.suffix):
                errors.append(source.name)
                continue
            name = source.stem
            if self.pd.mod_item(name) is not None:
                ignored.append(name)
                continue
            mod_dir = self.ctx.profile_mods_dir / name
            mod_dir.mkdir(parents=True, exist_ok=True)
            result = self._archive_backend().extract(source, mod_dir)
            if not result.ok:
                errors.append(source.name)
                shutil.rmtree(mod_dir, ignore_errors=True)
                continue
            (mod_dir / C.DOWNLOADS_DIR).mkdir(exist_ok=True)
            self.pd.add_mod(ModData(group=group, mod_name=name))
            created.append(name)
        if created:
            self.pd.initialise_groups()
            self.save()
        parts = [f"Mods created: {len(created) or 'None'}."]
        if ignored:
            parts.append(f"Already exist: {len(ignored)}.")
        if errors:
            parts.append(f"Errors: {len(errors)}.")
        return {
            "created": created,
            "ignored": ignored,
            "errors": errors,
            "message": " ".join(parts),
        }

    def paste_mod_sources(self, sources: list[Path], group: str | None = None) -> dict:
        """Paste mod folders / archives from the clipboard as new mods (VB ModPaste).

        Ports the essence of ``NIT.Paste.vb`` ``ModPaste`` for the mods pane: each
        clipboard source becomes a new mod under ``group``. A *directory* is copied
        verbatim into the profile (its folder name becomes the mod name); an
        *archive* is delegated to :meth:`add_mods_from_files` (extract into a new
        mod). A source whose mod name already exists is ignored — faithful to VB,
        which skips a paste target that already exists (NIT.Paste.vb:659-664), so a
        copy/paste within the same profile is a deliberate no-op. Anything that is
        neither a directory nor an extractable archive is an error. Returns
        ``{"created", "ignored", "errors", "message"}``.

        NOTE (divergence): VB derives the mod name from the source via
        ``ModNameFromFile`` (title-casing / roman-numeral normalisation via the
        LazWorks ``ToSentence`` helper). The port uses the source folder/stem name
        verbatim, matching the convention already used by :meth:`add_mods_from_files`.
        """
        import shutil

        from vaultkeeper.core import constants as C
        from vaultkeeper.core.archive import is_extractable

        group = group or C.GROUP_NONE
        archives = [Path(s) for s in sources if Path(s).is_file()]
        dirs = [Path(s) for s in sources if Path(s).is_dir()]

        created: list[str] = []
        ignored: list[str] = []
        errors: list[str] = []

        # Directories: copy the mod folder verbatim, skipping existing names.
        for source in dirs:
            name = source.name
            if self.pd.mod_item(name) is not None:
                ignored.append(name)
                continue
            dest = self.ctx.profile_mods_dir / name
            try:
                shutil.copytree(source, dest)
            except OSError:
                errors.append(name)
                shutil.rmtree(dest, ignore_errors=True)
                continue
            md = ModData(group=group, mod_name=name)
            self.pd.add_mod(md)
            self.pd.scan_mod_files(md, self.ctx.profile_mods_dir)
            created.append(name)
        if created:
            self.pd.initialise_groups()
            self.pd.update_file_states()
            self.pd.update_mod_states()
            self.save()

        # Archives: delegate to the validated Add-Mods-from-Files path.
        extractable = [a for a in archives if is_extractable(a.suffix)]
        errors.extend(a.name for a in archives if not is_extractable(a.suffix))
        if extractable:
            arch_result = self.add_mods_from_files(extractable, group)
            created.extend(arch_result["created"])
            ignored.extend(arch_result["ignored"])
            errors.extend(arch_result["errors"])

        parts = [f"Mods created: {len(created) or 'None'}."]
        if ignored:
            parts.append(f"Already exist: {len(ignored)}.")
        if errors:
            parts.append(f"Errors: {len(errors)}.")
        return {
            "created": created,
            "ignored": ignored,
            "errors": errors,
            "message": " ".join(parts),
        }

    def update_downloads(self, mod_names: list[str]) -> dict:
        """Move loose compressed files into each mod's ``_Downloads`` folder.

        Ports VB *Move Compressed Files to Mod's Downloads Folder*
        (``NIT.ModView.UpdateDownloads``): for every selected mod, any file
        sitting loose in the mod's folder whose extension is a recognised archive
        (zip/rar/7z/…/exe) is moved into the mod's ``_Downloads`` subfolder. These
        are downloaded archives, not tracked installer files, so the profile
        database is left untouched — exactly as the VB app does. Returns
        ``{"mods": processed, "files": moved, "errors": n}``.
        """
        import shutil

        from vaultkeeper.core import constants as C
        from vaultkeeper.core.archive import is_zip_extension

        mods = moved = errors = 0
        for name in mod_names:
            md = self.pd.mod_item(name)
            if md is None or md.is_group_item:
                continue
            mod_folder = self.ctx.profile_mods_dir / name
            if not mod_folder.is_dir():
                errors += 1
                continue
            downloads = mod_folder / C.DOWNLOADS_DIR
            try:
                downloads.mkdir(parents=True, exist_ok=True)
            except OSError:
                errors += 1
                continue
            mods += 1
            for entry in mod_folder.iterdir():
                if entry.is_file() and is_zip_extension(entry.suffix):
                    try:
                        shutil.move(str(entry), str(downloads / entry.name))
                        moved += 1
                    except OSError:
                        errors += 1
        return {"mods": mods, "files": moved, "errors": errors}

    def compress_mod_folders(self, mod_names: list[str], *, compress: bool = True) -> dict:
        """Toggle NTFS folder compression on each mod folder (VB Compress/Uncompress).

        VB's *Compress Mod Folder* (``IOSystem.CompressionOperations``) sets or
        clears the **NTFS Compressed attribute** on the folder via WMI — it is
        transparent filesystem compression, not archiving. That is a Windows-only
        feature with no macOS/Linux equivalent, so on those platforms we report it
        as unavailable rather than inventing a divergent behaviour (e.g. producing
        a 7-Zip archive the VB app would never create). On Windows we shell out to
        the built-in ``compact`` tool (the CLI equivalent of the WMI call).

        Returns ``{"applied": n, "available": bool, "message": str}``.
        """
        from vaultkeeper.game.locations import HostOS

        if HostOS.current() is not HostOS.WINDOWS:
            return {
                "applied": 0,
                "available": False,
                "message": (
                    "Folder compression is a Windows-only NTFS feature and is not "
                    "available on this platform."
                ),
            }

        import subprocess

        flag = "/c" if compress else "/u"
        applied = 0
        for name in mod_names:
            md = self.pd.mod_item(name)
            if md is None or md.is_group_item:
                continue
            folder = self.ctx.profile_mods_dir / name
            if not folder.is_dir():
                continue
            try:
                proc = subprocess.run(  # noqa: S603,S607 - fixed Windows system tool
                    ["compact", flag, "/s", "/i", "/q"],
                    cwd=str(folder),
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError:
                continue
            if proc.returncode == 0:
                applied += 1
        verb = "Compressed" if compress else "Uncompressed"
        return {
            "applied": applied,
            "available": True,
            "message": f"{verb} {applied} mod folder(s).",
        }

    def _archive_backend(self):
        """The archive extractor/creator (SevenZip by default, Fake in tests)."""
        if self._extractor is None:
            from vaultkeeper.core.archive import SevenZipExtractor

            self._extractor = SevenZipExtractor()
        return self._extractor

    def publish_zip_name(self, mod_name: str, version: str = "") -> str:
        """The ``.7z`` file name a publish will produce (VB ``ZipFileName``).

        ``<mod>[ <version>].7z`` — the version text (trailing dots trimmed) is
        appended after a space, or omitted when blank.
        """
        suffix = version.strip().rstrip(".")
        return f"{mod_name} {suffix}.7z" if suffix else f"{mod_name}.7z"

    def publish_mod(self, mod_name: str, *, version: str = "") -> dict:
        """Archive a mod into a distributable ``.7z`` under ``_Published`` (VB PublishMod).

        Ports the PublishMod operation faithfully: create
        ``<mod>/_Published/<mod>[ <version>].7z`` from the mod folder's contents,
        excluding the private ``_PlayTime``/``_Downloads``/``_History``/``_Published``
        items (VB ``-x!`` list). If the mod has an installer wizard, its file
        references are re-rooted under the archive folder for the duration of the
        publish (``rewrite_for_publish``) and the original file is restored
        afterwards. Returns ``{"ok", "path", "zip_name", "message"}``.

        The optional *Generate Installation Guide* step is deferred (the VB RTF guide
        templates are not bundled). The published folder is the mod's, not a chosen
        destination — VB has no destination picker.
        """
        from vaultkeeper.core import constants as C
        from vaultkeeper.game.wizard import (
            WIZARD_FILE,
            archive_folder_name,
            rewrite_for_publish,
        )

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return _publish_result(False, message=f"Unknown mod: {mod_name}")
        mod_folder = self.ctx.profile_mods_dir / mod_name
        if not mod_folder.is_dir():
            return _publish_result(False, message=f"Mod folder missing: {mod_name}")

        backend = self._archive_backend()
        if not backend.available:
            return _publish_result(
                False, message="7-Zip is not available; cannot publish."
            )

        zip_name = self.publish_zip_name(mod_name, version)
        published_dir = mod_folder / C.PUBLISHED_DIR
        archive = published_dir / zip_name
        try:
            published_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _publish_result(
                False, message=f"Unable to create the {C.PUBLISHED_DIR} folder: {exc}"
            )

        # Re-root the wizard's file references under the archive folder, keeping the
        # original text to restore after the archive is built (VB non-destructive).
        wizard_file = mod_folder / WIZARD_FILE
        original_wizard = None
        if wizard_file.is_file():
            try:
                original_wizard = wizard_file.read_text(
                    encoding="utf-8", errors="replace"
                )
                wizard_file.write_text(
                    rewrite_for_publish(original_wizard, archive_folder_name(zip_name)),
                    encoding="utf-8",
                )
            except OSError:
                original_wizard = None

        exclude = [
            C.PLAY_TIME_FILE,
            C.DOWNLOADS_DIR,
            C.HISTORY_DIR,
            C.PUBLISHED_DIR,
        ]
        try:
            # Archive the folder's contents (VB "<ModPath>\*"), paths relative to it.
            result = backend.create(
                archive, [Path("*")], base_dir=mod_folder, exclude=exclude
            )
        finally:
            if original_wizard is not None:
                import contextlib

                with contextlib.suppress(OSError):
                    wizard_file.write_text(original_wizard, encoding="utf-8")

        if result.ok:
            return _publish_result(
                True,
                path=str(archive),
                zip_name=zip_name,
                message=f"Published {mod_name} to {zip_name}",
            )
        return _publish_result(
            False, message=result.error or f"Failed to publish {mod_name}"
        )

    def create_installer(self, mod_name: str) -> bool:
        """Mark a mod as an installer (write its identifier) and scan its files.

        Ports the essence of VB Create Installer: drop the ``.nitins`` identifier into
        the mod's ``nitconfig`` folder, (re)scan the ``.Mod Installer`` payload, and
        recompute states. Returns True if the mod is now an installer.
        """
        from vaultkeeper.core import constants as C

        return self._create_identifier(mod_name, C.EXT_INSTALLER)

    def create_restorer(self, mod_name: str) -> bool:
        """Mark a mod as a restorer (``.nitres`` identifier); VB Create Restorer."""
        from vaultkeeper.core import constants as C

        return self._create_identifier(mod_name, C.EXT_RESTORER)

    def convert_restorer(self, mod_name: str) -> int:
        """Convert a Restorer into an installable Mod (VB ``MsConvertRestorer``).

        VB (``NIT.Menu.vb`` MsConvertRestorer_Click @2738) moves the restorer's
        payload folders into ``_Downloads`` and re-runs Create Installer. The port's
        mod *type* is identifier-based — a ``<mod>.nitres`` vs ``<mod>.nitins`` file
        in ``nitconfig`` — and the payload lives in ``.Mod Installer`` regardless of
        type, so conversion simply swaps the identifier and rescans: the same
        observable end state (the mod becomes an installer). The payload does not
        need relocating in the port's model (noted divergence).

        Returns ``-1`` when the mod is missing or is not a restorer, ``0`` when the
        restorer has no payload files to convert (VB "The Restorer does not contain
        any files to convert."), and ``1`` when converted.
        """
        from vaultkeeper.core import constants as C

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item or not md.is_restorer():
            return -1
        # VB gathers folders from files whose extension isn't the restorer marker;
        # if there are none, there is nothing to convert.
        payload = [fk for fk in md.files if fk.extension.lower() != C.EXT_RESTORER]
        if not payload:
            return 0
        # Drop the restorer identifier file + its FileKey via the safe removal path
        # (a plain rescan only *adds* keys, so the stale .nitres would linger).
        self._remove_mod_files(
            mod_name, lambda fk: fk.extension.lower() == C.EXT_RESTORER
        )
        # Write the installer identifier + rescan + recompute states + persist.
        self.create_installer(mod_name)
        return 1

    def wizard_install_prompt(self, mod_name: str) -> dict:
        """The install-time wizard choices to present, if any (VB ``RunWizard``).

        Returns ``{"run_wizard", "title", "select_one_text", "select_many_text",
        "choices": [{key,display}], "preferences": [{key,display,checked}]}``. The
        dialog presents these (SelectOne → pick one; SelectMany → check any) and feeds
        the decisions back into :meth:`build_installer_payload`.
        """
        from vaultkeeper.game.wizard import load_wizard

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {"run_wizard": False}
        info = load_wizard(self.ctx.profile_mods_dir / mod_name, mod_name)
        if info is None or not info.run_wizard:
            return {"run_wizard": False}
        return {
            "run_wizard": True,
            "title": info.title,
            "select_one_text": info.select_one_text,
            "select_many_text": info.select_many_text,
            "choices": [{"key": k, "display": v} for k, v in info.select_one.items()],
            "preferences": [
                {"key": p.key, "display": p.display, "checked": p.checked}
                for p in info.select_many
            ],
        }

    def build_installer_payload(
        self,
        mod_name: str,
        *,
        convert_bik: bool | None = None,
        wizard_choice: str | None = None,
        wizard_checked: set[str] | None = None,
    ) -> dict:
        """Populate a mod's ``.Mod Installer`` payload from its raw/downloaded files.

        The faithful heart of VB Create Installer (``CreateInstaller``): scan the mod
        folder, extract any downloaded archives (via the injected extractor seam),
        analyse every file through the Mapper into the ``CopyList``, then copy each
        winning file into ``.Mod Installer/<folder>/<filename>``. When ``convert_bik``
        is on (defaults to the profile's ``convert_bik_files`` setting), ``.bik``
        movies are converted to ``.wbm`` via ffmpeg and the ``.wbm`` copied instead
        (VB ``BgConverter``). Afterwards the mod is (re)marked an installer, its file
        list rescanned and states recomputed, and the profile persisted.

        Bounded (see ``game/installer_build``): the ``nwnpatch.ini`` patch-hak
        reassignment and the wizard select-one/many modal flow are deferred. Returns
        ``{"ok", "copied", "excluded", "archives", "converted", "message"}``.
        """
        import tempfile

        from vaultkeeper.core import constants as C
        from vaultkeeper.core import fs
        from vaultkeeper.game.installer_build import build_copy_plan

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {
                "ok": False,
                "copied": 0,
                "excluded": 0,
                "archives": 0,
                "converted": 0,
                "message": f"Unknown mod: {mod_name}",
            }

        if convert_bik is None:
            convert_bik = self._convert_bik_files()

        mod_folder = self.ctx.profile_mods_dir / mod_name
        installer = mod_folder / C.MOD_INSTALLER_DIR
        installer.mkdir(parents=True, exist_ok=True)

        # RunWizard: resolve the installer wizard's ignore list from the decisions.
        ignore = self._wizard_ignore_paths(mod_folder, mod_name, wizard_choice, wizard_checked)

        converted = 0
        # Extract archives into a temp area that survives until the copy is done.
        with tempfile.TemporaryDirectory(prefix="vk-installer-") as extract_dir:
            plan = build_copy_plan(
                mod_name,
                mod_folder,
                mapper=self.ctx.mapper,
                extractor=self._archive_backend(),
                extract_root=Path(extract_dir),
                convert_bik=convert_bik,
                ignore=ignore,
            )
            copied = 0
            for item in plan.items:
                dest = installer / item.folder / item.filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    fs.copy_file(item.source, dest, overwrite=True)
                    copied += 1
                except OSError:
                    continue

            # BIK→WBM: convert each collected .bik and copy the .wbm into the movies
            # folder the Mapper assigns for it (VB BgConverter → WbmFiles copy).
            if convert_bik and plan.bik_files:
                converted = self._convert_bik_movies(plan.bik_files, installer, Path(extract_dir))

        # Persist the patch-hak ordering (VB UpdateSequenceFile): add this mod's
        # patch-folder haks to the global PatchFileSequence.txt.
        self._update_patch_sequence(plan)

        # Mark as an installer; _create_identifier rescans the payload, recomputes
        # file/mod states and persists (like add_files_to_mod's tail).
        self._create_identifier(mod_name, C.EXT_INSTALLER)

        return {
            "ok": True,
            "copied": copied,
            "excluded": len(plan.excluded),
            "archives": plan.archives_extracted,
            "converted": converted,
            "message": (
                f"Built installer for {mod_name}: {copied} file(s) copied"
                + (
                    f", {plan.archives_extracted} archive(s) extracted"
                    if plan.archives_extracted
                    else ""
                )
                + (f", {converted} movie(s) converted" if converted else "")
                + (f", {len(plan.excluded)} excluded" if plan.excluded else "")
                + "."
            ),
        }

    def _convert_bik_files(self) -> bool:
        """The profile's BIK→WBM preference (VB ``ProfileInfo.ConvertBikFiles``)."""
        from vaultkeeper.config.settings import load_settings

        settings = load_settings(self._settings_path)
        return bool(getattr(settings, "convert_bik_files", False))

    def _wizard_ignore_paths(
        self,
        mod_folder: Path,
        mod_name: str,
        wizard_choice: str | None,
        wizard_checked: set[str] | None,
    ) -> set[Path]:
        """Resolve the installer wizard's ignore list for a build (VB ``RunWizard``)."""
        from vaultkeeper.game.wizard import (
            load_wizard,
            resolve_wizard_ignores,
            wizard_ignore_paths,
        )

        info = load_wizard(mod_folder, mod_name)
        if info is None or not info.run_wizard:
            return set()
        keys = resolve_wizard_ignores(
            info, chosen_one=wizard_choice, checked_many=wizard_checked
        )
        return wizard_ignore_paths(mod_folder, keys)

    def _update_patch_sequence(self, plan) -> None:  # noqa: ANN001
        """Add a plan's patch-folder haks to the persisted sequence (VB UpdateSequenceFile)."""
        from vaultkeeper.core.hak_patch import PATCH_FOLDER, update_patch_sequence

        stems = [
            Path(item.filename).stem
            for item in plan.items
            if item.folder.lower() == PATCH_FOLDER
            and item.filename.lower().endswith(".hak")
        ]
        if stems:
            update_patch_sequence(self._profile_data_dir(), stems)

    # -- Hak-patch editor (VB HakPatchEditor / HakPatchManager) ------------ #
    def patch_hak_sequence(self) -> list[str]:
        """The ordered patch-hak load sequence for the editor (VB ``HakPatchManager``).

        The persisted sequence reconciled with the haks actually installed in the
        game's ``patch`` folder: saved order first (installed only), then any newly
        installed patch-haks appended (VB ``ValidateAll`` + ``PatchSequence``).
        """
        from vaultkeeper.core.hak_patch import read_patch_sequence

        self._hpm.sequence = read_patch_sequence(self._profile_data_dir())
        return self._hpm.ordered_haks()

    def save_patch_hak_sequence(self, order: list[str]) -> None:
        """Persist a new patch-hak order and regenerate ``nwnpatch.ini`` (VB ``BtSave_Click``).

        The order is written to the NIT-managed ``PatchFileSequence.txt``; the game's
        ``nwnpatch.ini`` (which NIT already owns and rebuilds on every install, backing
        up the original once) is regenerated so the new order takes effect.
        """
        from vaultkeeper.core.hak_patch import save_patch_sequence

        save_patch_sequence(self._profile_data_dir(), order)
        self._hpm.sequence = list(order)
        if self._hpm.installed_patch_haks():
            self._hpm.create_nwn_patch_ini_file()

    def _bik_converter(self):
        """The BIK→WBM converter (ffmpeg by default, Fake in tests)."""
        if self._bik_backend is None:
            from vaultkeeper.game.bik_convert import BikConverter

            self._bik_backend = BikConverter()
        return self._bik_backend

    def _convert_bik_movies(
        self, bik_files: list[Path], installer: Path, work_dir: Path
    ) -> int:
        """Convert each ``.bik`` to ``.wbm`` and copy it into the installer (VB BgConverter)."""
        from vaultkeeper.core import fs

        converter = self._bik_converter()
        if not converter.available:
            return 0
        converted = 0
        for bik in bik_files:
            wbm_name = f"{bik.stem}.wbm"
            wbm_tmp = work_dir / "wbm" / wbm_name
            if not converter.convert(bik, wbm_tmp):
                continue
            folder = self.ctx.mapper.get_mapped_folder(wbm_name)
            if not folder:
                continue
            dest = installer / folder / wbm_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                fs.copy_file(wbm_tmp, dest, overwrite=True)
                converted += 1
            except OSError:
                continue
        return converted

    # -- Create Missing Installers (VB CreateMissingInstallers) ------------ #
    def _profile_data_dir(self) -> Path:
        """The per-profile data folder (VB ``Paths.ProfileData``)."""
        return self.data_dir() / self.ctx.profile_mods_dir.name

    def _missing_installer_exclude_file(self) -> Path:
        """The persisted exclude list for Create Missing Installers (VB file name)."""
        return self._profile_data_dir() / "Exclude from missing Installers.txt"

    def mods_missing_installer(self) -> list[str]:
        """Non-group mods whose ``.Mod Installer`` folder does not exist (VB filter).

        VB ``MsCreateMissingInstallers``: ``Not IsGroupItem AndAlso Not
        HasModInstaller`` (``HasModInstaller`` = the ``.Mod Installer`` directory
        exists on disk), Windows-sorted.
        """
        from functools import cmp_to_key

        from vaultkeeper.core import constants as C
        from vaultkeeper.core.win_sort import win_compare

        names = [
            md.mod_name
            for md in self.pd.mod_list.values()
            if not md.is_group_item
            and not (self.ctx.profile_mods_dir / md.mod_name / C.MOD_INSTALLER_DIR).is_dir()
        ]
        return sorted(names, key=cmp_to_key(win_compare))

    def missing_installer_report(self) -> dict:
        """Mods lacking an installer plus the persisted exclusions (VB dialog load).

        Returns ``{"mods": [...all missing...], "excluded": [...persisted, still
        missing...]}``. Stale exclusions (mods that now have an installer) are
        dropped, matching the VB load which prunes the exclude list to ``ModList``.
        """
        missing = self.mods_missing_installer()
        lower = {m.lower() for m in missing}
        excluded = [e for e in self._read_missing_installer_excludes() if e.lower() in lower]
        return {"mods": missing, "excluded": excluded}

    def _read_missing_installer_excludes(self) -> list[str]:
        path = self._missing_installer_exclude_file()
        if not path.is_file():
            return []
        try:
            return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            return []

    def save_missing_installer_excludes(self, excludes: list[str]) -> None:
        """Persist the Create-Missing-Installers exclude list (VB ``ExcludeListFile``)."""
        path = self._missing_installer_exclude_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(excludes) + ("\n" if excludes else ""), encoding="utf-8")
        except OSError:
            pass

    def create_missing_installers(self, mod_names: list[str]) -> dict:
        """Build installers for the selected mods (VB ``ProcessCreateInstaller``).

        Builds each mod's installer payload (:meth:`build_installer_payload`). The
        exclude-list bookkeeping lives with the dialog (VB ``BtCreate``), which calls
        :meth:`save_missing_installer_excludes`. Returns ``{"built","copied","message"}``.
        """
        built = copied = 0
        for name in mod_names:
            result = self.build_installer_payload(name)
            if result["ok"]:
                built += 1
                copied += result["copied"]
        return {
            "built": built,
            "copied": copied,
            "message": f"Created {built} missing installer(s); {copied} file(s) copied.",
        }

    def _create_identifier(self, mod_name: str, extension: str) -> bool:
        from vaultkeeper.core import constants as C

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return False
        nit_dir = (
            self.ctx.profile_mods_dir / mod_name / C.MOD_INSTALLER_DIR / C.MOD_NIT_DIR
        )
        nit_dir.mkdir(parents=True, exist_ok=True)
        (nit_dir / f"{mod_name}{extension}").write_text("", encoding="utf-8")
        self.pd.scan_mod_files(md, self.ctx.profile_mods_dir)
        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.save()
        return md.is_installer() if extension == C.EXT_INSTALLER else md.is_restorer()

    # -- Groups ------------------------------------------------------------ #
    def create_group(self, name: str) -> bool:
        """Create an (empty) group row. Returns False if the name already exists."""
        if not name or name in self.pd.mod_list:
            return False
        self.pd.move_mods_to_group([], name)  # creates the group row
        self.save()
        return True

    def move_to_group(self, names: list[str], group: str) -> None:
        """Move the named mods into ``group`` (creating it if new); persist."""
        self.pd.move_mods_to_group(names, group)
        self.save()

    def rename_group(self, old: str, new: str) -> bool:
        """Rename a (non-reserved) group and its members; persist on success."""
        ok = self.pd.rename_group(old, new)
        if ok:
            self.save()
        return ok

    def group_names(self) -> list[str]:
        """Visible (non-reserved) group names."""
        return self.pd.group_keys

    # -- Mod notes (per-mod RTF) ------------------------------------------- #
    def mod_notes_path(self, mod_name: str) -> Path:
        """The mod's notes file (VB ``ModData.NotesFile`` = ``…/Mod Notes/<mod>.rtf``)."""
        from vaultkeeper.app_paths import data_root

        base = self.store_path.parent if self.store_path else data_root()
        return base / self.ctx.profile_mods_dir.name / "Mod Notes" / f"{mod_name}.rtf"

    def read_notes(self, mod_name: str) -> str:
        """The mod's notes as plain text (empty if none)."""
        from vaultkeeper.core.rtf import read_rtf_text

        path = self.mod_notes_path(mod_name)
        if not path.is_file():
            return ""
        try:
            return read_rtf_text(
                path.read_text(encoding="utf-8", errors="replace")
            ).strip("\n")
        except OSError:
            return ""

    def save_notes(self, mod_name: str, text: str) -> None:
        """Write the mod's notes as an RTF file (deleting it when empty)."""
        from vaultkeeper.core.rtf import write_rtf

        path = self.mod_notes_path(mod_name)
        if text.strip() == "":
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(write_rtf(text.split("\n")), encoding="utf-8")

    # -- Maintenance (Tools menu) ----------------------------------------- #
    def validate_profile_data(self) -> str:
        """Remove dependencies on non-existent mods + recompute states (VB Validate)."""
        removed = self.pd.validate_dependencies()
        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.save()
        return f"Validation complete. Removed {removed} invalid dependency(ies)."

    # -- Validate Mods (VB MsValidateMods / ValidateMods) ------------------ #
    def validate_notes(self) -> int:
        """Delete orphaned Mod Notes files (VB ``ProfileData.ValidateNotes``).

        A notes file is orphaned when it is not an ``.rtf`` for a known mod *and* no
        mod folder of that name exists (the latter guards a just-added mod whose DB
        row is not yet present). Returns the number deleted.
        """
        notes_dir = self.mod_notes_path("_").parent
        if not notes_dir.is_dir():
            return 0
        removed = 0
        for path in sorted(p for p in notes_dir.iterdir() if p.is_file()):
            orphan = path.suffix.lower() != ".rtf" or path.stem not in self.pd.mod_list
            if orphan and not (self.ctx.profile_mods_dir / path.stem).is_dir():
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed

    def _validate_mod_patch_ini(self, md: ModData) -> str:
        """Create/delete a mod's ``nwnpatch.ini`` from its patch-folder haks.

        Faithful port of ``HakPatchManager.ValidateMod``: skip restorers, file-less
        mods and mods with no haks (leaving INI-only installers alone). If the mod
        has ``.hak`` files in the ``patch`` folder, write
        ``.Mod Installer/nwn/nwnpatch.ini`` listing them and register the file; else
        delete any existing mod ini and drop its key. Returns
        ``"created"``/``"deleted"``/``"none"``.

        The global patch-hak sequence file (VB ``PatchSequence`` ordering) is
        deferred — entries are ordered by Windows sort, which is deterministic and
        correct for a single mod's own haks.
        """
        from functools import cmp_to_key

        from vaultkeeper.core import constants as C
        from vaultkeeper.core.win_sort import win_compare

        if md is None or md.is_group_item or md.is_restorer() or not md.files:
            return "none"
        hak_files = [fk for fk in md.files if fk.extension.lower() == ".hak"]
        if not hak_files:
            return "none"

        patch_folder = self.ctx.mapper.get_secondary_folder(".hak")
        patch_haks = [fk for fk in hak_files if fk.folder.lower() == patch_folder.lower()]
        mod_ini = (
            self.ctx.profile_mods_dir
            / md.mod_name
            / C.MOD_INSTALLER_DIR
            / C.MOD_ROOT_FOLDER
            / C.PATCH_INI_FILE
        )

        if patch_haks:
            stems = sorted(
                (Path(fk.filename).stem for fk in patch_haks),
                key=cmp_to_key(win_compare),
            )
            lines = ["[Patch]"] + [f"PatchFile{i:03d}={s}" for i, s in enumerate(stems)]
            existed = mod_ini.is_file()
            mod_ini.parent.mkdir(parents=True, exist_ok=True)
            mod_ini.write_text("\n".join(lines) + "\n", encoding="utf-8")
            # Register the ini file key (scan only adds files not already tracked).
            self.pd.scan_mod_files(md, self.ctx.profile_mods_dir)
            return "unchanged" if existed else "created"

        if mod_ini.is_file():
            mod_ini.unlink()
            fk = FileKeyInfo(md.group, md.mod_name, C.MOD_ROOT_FOLDER, C.PATCH_INI_FILE)
            self.pd.file_list.pop(fk, None)
            if fk in md.files:
                md.files.remove(fk)
            self.pd.changes.file.removed(fk)
            return "deleted"
        return "none"

    def validate_mods(self) -> str:
        """Validate all mods and hak-patch information (VB ``ValidateMods``).

        Runs the maintenance pass MsValidateMods performs: prune dependencies on
        missing mods, delete orphaned Mod Notes, (re)build each mod's
        ``nwnpatch.ini`` from its patch haks, and rebuild the game's ``nwnpatch.ini``
        from the installed patch haks. Recomputes states and persists.
        """
        removed_deps = self.pd.validate_dependencies()
        orphaned_notes = self.validate_notes()
        ini_created = ini_deleted = 0
        for md in list(self.pd.mod_list.values()):
            result = self._validate_mod_patch_ini(md)
            if result == "created":
                ini_created += 1
            elif result == "deleted":
                ini_deleted += 1
        self._hpm.create_nwn_patch_ini_file()
        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.save()
        return (
            f"Validated mods. Dependencies removed: {removed_deps}. "
            f"Orphaned notes: {orphaned_notes}. "
            f"Patch INI created: {ini_created}, deleted: {ini_deleted}."
        )

    def movie_files_report(self) -> dict:
        """Installer files whose movie format is wrong for the edition (VB MsValidateMovieFiles).

        EE uses ``.wbm`` movies, so ``.bik`` files are invalid; classic NWN is the
        reverse. Returns ``{"count", "mods", "summary", "text"}`` — the report text
        lists the affected files grouped by mod with a "Recreate the Mod Installers"
        instruction (VB ``ShowText`` body). Read-only: NIT does not auto-fix; the
        user re-creates the installer so the converter picks the right format.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare

        invalid_ext = ".bik" if self.ctx.is_ee else ".wbm"
        invalid = [
            fk for fk in self.pd.file_list if fk.extension.lower() == invalid_ext
        ]
        invalid.sort(
            key=cmp_to_key(
                lambda a, b: win_compare(
                    f"{a.mod_name}\\{a.file_key}", f"{b.mod_name}\\{b.file_key}"
                )
            )
        )
        mods: list[str] = []
        for fk in invalid:
            if fk.mod_name not in mods:
                mods.append(fk.mod_name)

        summary = f"Invalid movie files: {len(invalid) or 'None'}."
        if mods:
            summary += f" Mods affected: {len(mods)}."

        lines = [
            "",
            "Recreate the Mod Installers for each Mod listed below to ensure the "
            "correct movie file format is used.",
        ]
        current = ""
        for fk in invalid:
            if fk.mod_name != current:
                current = fk.mod_name
                lines += ["", fk.mod_name]
            lines.append(f"    {fk.filename}")
        return {
            "count": len(invalid),
            "mods": mods,
            "summary": summary,
            "text": "\n".join(lines),
        }

    def calculate_crcs(self) -> str:
        """Recompute CRC-32 checksums for pending files and refresh states."""
        self.pd.calculate_checksums(self.ctx.profile_mods_dir, self.ctx.game_folders)
        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.save()
        return "CRC calculation complete."

    def rescan_installed_state(self) -> str:
        """Recompute install state for imported mods from the live game, and persist.

        For a profile whose mods came from a legacy import (definitions + file keys,
        no on-disk installer files), this scans the mapped game folders and marks
        each mod's files installed when the game contains them — the manual form of
        the automatic first-open rebuild. Use it to refresh after the game changes.
        """
        self.pd.rescan_installed_state(
            self.ctx.game_folders, root_folder_name=self.ctx.root_folder_name
        )
        self.save()
        total, installed = self.counts()
        return f"Rescan complete: {installed:,} of {total:,} mods installed."

    def rebuild_database(self) -> str:
        """Rebuild the profile database from disk (VB Rebuild Database)."""
        # An imported profile has mod definitions + file keys but no on-disk
        # installer folders — a full rescan would find nothing and wipe it. Refresh
        # install state from the live game instead (keep the imported mods).
        mods_dir = self.ctx.profile_mods_dir
        has_mod_folders = mods_dir.is_dir() and any(p.is_dir() for p in mods_dir.iterdir())
        if not has_mod_folders and _has_unscanned_mods(self.pd):
            return self.rescan_installed_state()

        self.pd = ProfileData()
        self.pd.scan_mods(self.ctx.profile_mods_dir)
        self.pd.scan_installed(
            self.ctx.game_folders, root_folder_name=self.ctx.root_folder_name
        )
        self.pd.calculate_checksums(self.ctx.profile_mods_dir, self.ctx.game_folders)
        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.pd.changes.reset_changes()
        self.pd.initialise_groups()
        self._rebuild_engine()
        self.save()
        total, installed = self.counts()
        return f"Database rebuilt: {total:,} mods, {installed:,} installed."

    def _rebuild_engine(self) -> None:
        """Rebuild the engine/hak-patch against ``self.pd`` and drop the play loop."""
        self._hpm = HakPatchManager(self.pd, self.ctx.game_root / "nwnpatch.ini")
        self.engine = ModInstallationManager(
            self.pd, self.ctx, hak_patch=self._hpm.create_nwn_patch_ini_file,
            on_save=self.save,
        )
        self._play_loop = None

    # -- Backup / restore (File menu) ------------------------------------- #
    def data_dir(self) -> Path:
        """The store's Data directory (where profile DBs / play data / notes live)."""
        from vaultkeeper.app_paths import data_root

        return self.store_path.parent if self.store_path else data_root()

    def backup_data(self, dest_zip: Path) -> str:
        """Zip the whole Data directory to ``dest_zip`` (VB Backup Data)."""
        import zipfile

        data = self.data_dir()
        if not data.is_dir():
            return "There is no data to back up yet."
        count = 0
        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(data.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(data))
                    count += 1
        return f"Backed up {count:,} file(s) to {dest_zip.name}."

    def restore_data(self, src_zip: Path) -> str:
        """Restore a backup zip into the Data directory and reload (VB Restore Data)."""
        import zipfile

        data = self.data_dir()
        data.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src_zip) as archive:
            archive.extractall(data)
        if self.store_path is not None and self.store_path.is_file():
            restored = load_profile(self.store_path)
            if restored is not None:
                self.pd = restored
                self.pd.initialise_groups()
                self._rebuild_engine()
        return f"Restored data from {src_zip.name}."

    # -- Recovery (VB MsRecoverGroups / MsRecoverModProperties) ------------ #
    def recover_groups(self, source: dict | Path | str) -> int:
        """Recover Group assignments from another profile's data (VB
        ``MsRecoverGroups_Click``, NIT.Menu.vb:4898 → ``BgRecoverGroups`` @5030).

        ``source`` is whatever :func:`vaultkeeper.game.recovery.read_group_info`
        accepts (a parsed profile dict, or a path to a ``<profile>.json``). VB
        (``BgRecoverGroups`` @5051-5063) creates a group row for every recovered
        group that does not already exist (``pd.AddGroups``), then moves a mod into
        its recovered group ONLY when the mod still sits in a hidden/reserved
        pseudo-group (``mdi.Group <> key AndAlso mdi.IsHiddenGroup``) — it never
        overrides a mod the user has since organised. Persists. Returns the number
        of mods moved (VB "Mod Group changes").
        """
        from vaultkeeper.game.recovery import read_group_info

        group_info = read_group_info(source)
        # VB pd.AddGroups: ensure each recovered group exists as a row, even empty.
        for group in dict.fromkeys(group_info.values()):
            if group and group not in self.pd.mod_list:
                self.pd.move_mods_to_group([], group)
        changed = 0
        for mod_name, group in group_info.items():
            md = self.pd.mod_item(mod_name)
            if md is None or md.is_group_item:
                continue
            if group and md.group != group and md.is_hidden_group:
                self.pd.move_mods_to_group([mod_name], group)
                changed += 1
        self.save()
        return changed

    def recover_mod_properties(self, source: dict | Path | str) -> int:
        """Recover user-editable mod properties from another profile's data (VB
        ``MsRecoverModProperties_Click``, NIT.Menu.vb:5077 →
        ``ProfileData.RecoverUserData`` @2730).

        For every mod that still exists in the active profile, copies the SIX
        properties ``RecoverUserData`` restores — Rating, BestWeapon, LevelStart,
        LevelEnd, HenchCount, WebLink (ProfileData.vb:2755-2785). VB deliberately
        does NOT restore DateCompleted/CompletedCount, so neither does this.
        Persists. Returns the number of mods with at least one changed property.
        """
        from vaultkeeper.core.state import Ratings, Weapon
        from vaultkeeper.game.recovery import read_property_info

        property_info = read_property_info(source)
        changed = 0
        for mod_name, props in property_info.items():
            md = self.pd.mod_item(mod_name)
            if md is None or md.is_group_item:
                continue
            rating = Ratings(props["rating"])
            best_weapon = Weapon(props["best_weapon"])
            web_link = props["web_link"] or ""
            mod_changed = False
            if md.rating != rating:
                md.rating = rating
                mod_changed = True
            if md.best_weapon != best_weapon:
                md.best_weapon = best_weapon
                mod_changed = True
            if md.level_start != props["level_start"]:
                md.level_start = props["level_start"]
                mod_changed = True
            if md.level_end != props["level_end"]:
                md.level_end = props["level_end"]
                mod_changed = True
            if md.hench_count != props["hench_count"]:
                md.hench_count = props["hench_count"]
                mod_changed = True
            if md.web_link != web_link:
                md.web_link = web_link
                mod_changed = True
            if mod_changed:
                changed += 1
        self.save()
        return changed

    # -- Engine maintenance ------------------------------------------------ #
    def anneal(self) -> str:
        """Repair conflict winners for all installed mods (VB Anneal); persist."""
        self.engine.anneal(None)
        self.save()
        return "Anneal complete."

    # -- Play loop (Phase 5) ---------------------------------------------- #
    @property
    def play_loop(self) -> PlayLoop | None:
        """The play-tracking loop for this profile (None if no game-user dir)."""
        if self._play_loop is not None:
            return self._play_loop
        if self.ctx.game_user_dir is None:
            return None
        from vaultkeeper.app_paths import data_root

        data_dir = self.store_path.parent if self.store_path else data_root()
        self._play_loop = PlayLoop(
            self.pd,
            profile_mods_dir=self.ctx.profile_mods_dir,
            data_dir=data_dir,
            saves_dir=self.ctx.game_user_dir / "saves",
            log_path=self.ctx.game_user_dir / "logs" / "nwclientlog1.txt",
            on_save=self.save,
            prompter=self.play_prompter,
            download_rules=self._load_download_rules(data_dir),
        )
        return self._play_loop

    # -- Vault downloads (candidate #3) ----------------------------------- #
    def _make_scraper(self):
        from vaultkeeper.app_paths import data_root
        from vaultkeeper.vault.download_rules import DownloadRules
        from vaultkeeper.vault.http import RequestsHttpClient
        from vaultkeeper.vault.scraper import VaultScraper

        if self._http is None:
            self._http = RequestsHttpClient()
        data_dir = self.store_path.parent if self.store_path else data_root()
        rules = self._load_download_rules(data_dir) or DownloadRules()
        return VaultScraper(rules, self._http)

    def scrape_project(self, url: str) -> list:
        """Scrape a Vault project page into a list of downloadable files."""
        return self._make_scraper().fetch_project(url)

    def project_required_projects(self, url: str) -> list[dict]:
        """The projects a Vault page lists as required (VB Required-Projects field).

        Each is a ``{"title", "url"}`` — the mods this project depends on (e.g.
        "CEP 2.6"). Surfaced by the Download Project dialog so the user can fetch the
        prerequisites too.
        """
        return self._make_scraper().fetch_required_projects(url)

    def download_project(
        self, files: list, mod_name: str, *, group: str | None = None, on_progress=None
    ) -> list:
        """Download files into ``mod_name``'s ``_Downloads``, creating the mod if new.

        Faithful to VB "Download a Project … to create or update a Mod": when
        ``mod_name`` isn't yet a managed mod it is created (under ``group``) so the
        Vault download lands in a real, ready-to-build mod; an existing mod is just
        updated. Returns the per-file download results.
        """
        from vaultkeeper.core import constants as C
        from vaultkeeper.vault.downloader import Downloader

        if mod_name and self.pd.mod_item(mod_name) is None:
            self.create_mod(mod_name, group)
        dest = self.ctx.profile_mods_dir / mod_name / C.DOWNLOADS_DIR
        dest.mkdir(parents=True, exist_ok=True)
        downloader = Downloader(
            self._http, scraper=self._make_scraper(), on_progress=on_progress
        )
        return downloader.download_all(files, dest)

    def suggested_mod_name(self, project_title: str) -> str:
        """A presentable mod folder name derived from a Vault project title.

        Strips characters illegal in a folder name, collapses whitespace, and
        capitalises each word so a de-slugged project title (``my project``) becomes a
        tidy default (``My Project``). It is only a convenience default — the Download
        Project dialog lets the user edit it before creating the mod.
        """
        import re

        cleaned = re.sub(r'[\\/:*?"<>|]+', " ", project_title or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return " ".join(w[:1].upper() + w[1:] for w in cleaned.split(" ") if w)

    def mark_download_status(self, files: list, mod_name: str) -> None:
        """Flag each project file DOWNLOADED when it already sits in the mod's downloads.

        Ports VB ``DownloadProject.IsDownloaded``: a file already present in the target
        mod's ``_Downloads`` is shown "Already downloaded" so it isn't needlessly
        re-fetched (the dialog unticks those by default; the user can re-tick to force a
        re-download). Files with no matching download are marked ``AVAILABLE``.
        """
        from vaultkeeper.core import constants as C
        from vaultkeeper.vault.downloader import _filename_from_url
        from vaultkeeper.vault.scraper_info import FileStatus

        downloads = self.ctx.profile_mods_dir / mod_name / C.DOWNLOADS_DIR
        existing = (
            {p.name.lower() for p in downloads.iterdir() if p.is_file()}
            if mod_name and downloads.is_dir()
            else set()
        )
        for vsi in files:
            if vsi.excluded:
                continue
            name = (
                vsi.local_filename
                or vsi.filename
                or _filename_from_url(vsi.direct_url or vsi.counter_url or "")
            )
            vsi.status = (
                FileStatus.DOWNLOADED if name.lower() in existing else FileStatus.AVAILABLE
            )

    def install_downloaded_project(
        self, files: list, mod_name: str, *, group: str | None = None, on_progress=None
    ) -> dict:
        """Download a project, build its installer, then install it (VB Install button).

        VB's Download Project *Install* downloads the marked files and, when done,
        builds the installer and installs the mod (``DownloadMarkedFiles`` →
        ``CreateInstallers`` → ``MsInstall``). Composes the existing steps:
        :meth:`download_project` (create-if-new + fetch) → :meth:`build_installer_payload`
        (extract downloads → payload) → :meth:`install`. Returns
        ``{"downloaded", "total", "built", "install_message"}``.
        """
        results = self.download_project(
            files, mod_name, group=group, on_progress=on_progress
        )
        downloaded = sum(1 for r in results if r.ok)
        build = self.build_installer_payload(mod_name)
        install_message = self.install([mod_name]) if build["ok"] else build["message"]
        return {
            "downloaded": downloaded,
            "total": len(results),
            "built": build["ok"],
            "install_message": install_message,
        }

    @staticmethod
    def _load_download_rules(data_dir: Path):
        """Load the cached Vault download rules (for GameMapper save-name rules)."""
        from vaultkeeper.vault.download_rules import DownloadRules

        rules_file = data_dir / "DownloadRules.txt"
        if rules_file.is_file():
            try:
                return DownloadRules.from_text(
                    rules_file.read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                return None
        return None

    def current_game_summary(self) -> str:
        """One-line description of the current game save (or a placeholder)."""
        loop = self.play_loop
        return loop.current_game_summary() if loop is not None else "No game saves"

    def launch_argv(self, *, toolset: bool = False, wait: bool = False) -> list[str]:
        """The command to launch NWN (or the toolset) for this install.

        With ``wait=True`` the argv runs a direct (awaitable) executable when one is
        available, so the caller can detect game exit and record the play session.
        """
        from vaultkeeper.game.game_launch import launch_argv
        from vaultkeeper.game.locations import HostOS

        return launch_argv(
            self.ctx.game_root,
            host=HostOS.current(),
            user_dir=self.ctx.game_user_dir,
            steam_app_id="704450" if self.ctx.is_ee else None,
            toolset=toolset,
            wait=wait,
        )

    def can_await_exit(self, *, toolset: bool = False) -> bool:
        """True if the game can be launched as an awaitable process (exit detected)."""
        from vaultkeeper.game.game_launch import run_binary
        from vaultkeeper.game.locations import HostOS

        return run_binary(self.ctx.game_root, HostOS.current(), toolset=toolset) is not None

    def process_play_session(self, started: datetime, stopped: datetime) -> dict:
        """Record a finished play session (log -> per-mod times -> persist)."""
        loop = self.play_loop
        return loop.process_session(started, stopped) if loop is not None else {}

    def mod_explorer_report(self) -> dict:
        """Every mod with its key properties, state and play time (VB ModExplorer)."""
        loop = self.play_loop
        rows = []
        for name in self.pd.sorted_mod_keys:
            md = self.pd.mod_item(name)
            if md is None:
                continue
            played = ""
            if loop is not None:
                span = loop.play_time(name)
                if span.total_seconds() > 0:
                    played = loop.play_data.format_time(span, "")
            rows.append(
                {
                    "mod": name,
                    "group": self.group_label(md.group),
                    "state": md.mod_state.name.replace("_", " ").title(),
                    "rating": md.rating.name.title(),
                    "files": len(md.files),
                    "played": played,
                    "completed": md.completed_count,
                }
            )
        return {"rows": rows, "count": len(rows)}

    def installation_report(self) -> dict:
        """Health/analysis of the installation (VB InstallationAnalyser).

        Totals plus the flagged files: game originals whose CRC changed, and
        installed files from an unknown source with a mapped extension.
        """
        total, installed = self.counts()
        changed = self.pd.changed_original_files()
        unknown = self.pd.unknown_source_files(self.ctx.mapper)
        issues = [
            {"category": "Changed original", "file": fk.file_key} for fk in changed
        ]
        issues += [
            {"category": "Unknown source", "file": fk.file_key} for fk in unknown
        ]
        issues.sort(key=lambda r: (r["category"], r["file"].lower()))
        return {
            "total_mods": total,
            "installed_mods": installed,
            "installed_files": len(self.pd.installed_list),
            "original_files": len(self.pd.original_file_keys()),
            "changed_originals": len(changed),
            "unknown_source": len(unknown),
            "issues": issues,
        }

    def installation_browser_report(self) -> dict:
        """Installed files grouped by NWN folder (VB InstallationAnalyser browser).

        Returns ``{"folders": [{"name", "count", "size", "size_bytes", "files":
        [{"filename", "source", "size", "modified"}]}], "total_size", "total_bytes"}``
        — the NWN-Folders list filtering a File-Name / Installation-Source table, with
        the total installed-file size. Built from the installed-file model.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare

        key = cmp_to_key(win_compare)
        buckets: dict[str, list] = {}
        for fk, ifd in self.pd.installed_list.items():
            buckets.setdefault(fk.folder, []).append((fk, ifd))

        folders = []
        total = 0
        for folder in sorted(buckets, key=key):
            entries = sorted(buckets[folder], key=lambda pair: key(pair[0].filename))
            files = []
            folder_size = 0
            for fk, ifd in entries:
                files.append(
                    {
                        "filename": fk.filename,
                        "source": ifd.installer,
                        "size": _fmt_size(ifd.byte_size),
                        "size_bytes": ifd.byte_size,
                        "modified": _fmt_date(ifd.modified),
                    }
                )
                folder_size += ifd.byte_size
            total += folder_size
            folders.append(
                {
                    "name": folder,
                    "count": len(files),
                    "size": _fmt_size(folder_size),
                    "size_bytes": folder_size,
                    "files": files,
                }
            )
        return {
            "folders": folders,
            "total_size": _fmt_size(total),
            "total_bytes": total,
        }

    # -- Installation sets (VB InstallationManager) ------------------------ #
    def _installation_sets_file(self) -> Path:
        """The persisted installation-sets database (VB ``pd.SaveInstallationSets``)."""
        return self._profile_data_dir() / "InstallationSets.json"

    def installed_by_group(self) -> dict[str, list[str]]:
        """Currently-installed mods grouped by group name, in display order.

        Faithful to VB ``InstallationManager.Checkpoint``: real mods only (not group
        rows), installed, excluding the auto-managed restorer group. Groups and mods
        are Windows natural-sorted.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare
        from vaultkeeper.game.start_screen import AUTO_GROUP

        buckets: dict[str, list[str]] = {}
        for name in self.pd.mod_keys:
            md = self.pd.mod_item(name)
            if md is None or md.is_group_item or not md.installed:
                continue
            if md.group == AUTO_GROUP:
                continue
            buckets.setdefault(md.group, []).append(md.mod_name)

        key = cmp_to_key(win_compare)
        return {g: sorted(buckets[g], key=key) for g in sorted(buckets, key=key)}

    def _current_installation_set(self):
        """Build the live "Current" set (VB ``CreateCurrent`` — always index 0)."""
        from vaultkeeper.game.installation_sets import (
            CURRENT_SET_NAME,
            SET_CURRENT,
            build_set,
        )

        return build_set(CURRENT_SET_NAME, SET_CURRENT, self.installed_by_group())

    def load_installation_sets(self) -> list:
        """Load the installation sets (VB ``LoadSets``): the live Current set first,
        then the persisted checkpoint/user sets, with stale groups/mods pruned."""
        from vaultkeeper.game.installation_sets import sets_from_json, validate_sets
        from vaultkeeper.persistence.json_store import read_json

        stored = sets_from_json(read_json(self._installation_sets_file(), default=[]))
        existing_mods = {
            md.mod_name: md.group
            for name in self.pd.mod_keys
            if (md := self.pd.mod_item(name)) is not None and not md.is_group_item
        }
        existing_groups = set(self.pd.group_keys) | {
            md.group for md in map(self.pd.mod_item, self.pd.mod_keys) if md is not None
        }
        removed = validate_sets(stored, existing_mods, existing_groups)
        if removed:
            self.save_installation_sets(stored)
        return [self._current_installation_set(), *stored]

    def save_installation_sets(self, sets: list) -> None:
        """Persist the checkpoint/user sets (the Current set is never written)."""
        from vaultkeeper.game.installation_sets import sets_to_json
        from vaultkeeper.persistence.json_store import write_json

        path = self._installation_sets_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, sets_to_json(sets))

    def create_installation_checkpoint(self) -> str:
        """Snapshot the current install state as a checkpoint set (VB ``CreateCheckpoint``).

        Returns the new set's name.
        """
        from vaultkeeper.game.installation_sets import (
            SET_CHECKPOINT,
            build_set,
            checkpoint_name,
        )

        name = checkpoint_name()
        stored = self.load_installation_sets()[1:]  # drop the live Current set
        stored.append(build_set(name, SET_CHECKPOINT, self.installed_by_group()))
        self.save_installation_sets(stored)
        return name

    def create_installation_set(self, name: str, *, from_current: bool = True) -> None:
        """Create a user-defined set (VB ``CreateSet``).

        ``from_current`` pre-fills it with the currently-installed mods (editable);
        otherwise it starts empty.
        """
        from vaultkeeper.game.installation_sets import SET_USER, build_set

        by_group = self.installed_by_group() if from_current else {}
        stored = self.load_installation_sets()[1:]
        stored.append(build_set(name, SET_USER, by_group))
        self.save_installation_sets(stored)

    def rename_installation_set(self, old_name: str, new_name: str) -> None:
        """Rename a set (VB ``RenameSet``); no-op if the name is missing/duplicate."""
        stored = self.load_installation_sets()[1:]
        names = {s.name for s in stored}
        if old_name not in names or new_name in names or not new_name.strip():
            return
        for s in stored:
            if s.name == old_name:
                s.name = new_name
        self.save_installation_sets(stored)

    def delete_installation_set(self, name: str) -> None:
        """Remove a set (VB ``RemoveSet``)."""
        stored = [s for s in self.load_installation_sets()[1:] if s.name != name]
        self.save_installation_sets(stored)

    def apply_installation_set(self, iset) -> str:  # noqa: ANN001
        """Install/uninstall to reach the set's desired states (VB ``BtApply``).

        Uninstalls the mods the set marks uninstalled, then installs those it marks
        installed (VB order), for the mods in the set whose state differs from now.
        Returns a status message.
        """
        from vaultkeeper.game.installation_sets import apply_diff

        current = {
            md.mod_name
            for name in self.pd.mod_keys
            if (md := self.pd.mod_item(name)) is not None
            and not md.is_group_item
            and md.installed
        }
        installs, uninstalls = apply_diff(iset, current)
        messages = []
        if uninstalls:
            messages.append(self.uninstall(uninstalls))
        if installs:
            messages.append(self.install(installs))
        if not messages:
            return "The installation set is already applied."
        return " ".join(m for m in messages if m)

    def dependencies_report(self) -> dict:
        """Each mod's declared dependencies and the mods that require it.

        Surfaces the ProfileData dependency graph (VB DependencyManager): a row per
        mod that either depends on something or is depended upon.
        """
        dependants = self.pd.get_dependants()
        rows = []
        for name in self.pd.sorted_mod_keys:
            md = self.pd.mod_item(name)
            if md is None:
                continue
            depends_on = sorted(md.dependencies)
            required_by = dependants.get(name, [])
            if depends_on or required_by:
                rows.append(
                    {
                        "mod": name,
                        "depends_on": depends_on,
                        "required_by": required_by,
                    }
                )
        return {"rows": rows, "count": len(rows)}

    def group_label(self, group: str) -> str:
        """A display label for a group key (sentinel buckets get friendly names)."""
        from vaultkeeper.core import constants as C

        if group == C.GROUP_NONE:
            return "No Group"
        if group == C.GROUP_INSTALLED:
            return "Installed by NWN"
        return group

    def dependency_editor_data(self, mod_name: str) -> dict:
        """Groups → mods and the current dependencies for editing (VB DependencyManager).

        Returns ``{"mod", "groups": [{"name", "mods": [...]}], "dependencies": [...]}``.
        Groups mirror the VB LvGroups → LvMods → LvDependencies layout: every non-group
        mod (except the edited mod itself and mods in restorer groups) bucketed by its
        group's display label, plus the edited mod's current dependency list.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {"mod": mod_name, "groups": [], "dependencies": []}

        key = cmp_to_key(win_compare)
        buckets: dict[str, list[str]] = {}
        for name, other in self.pd.mod_list.items():
            if other.is_group_item or name == mod_name:
                continue
            if "restorer" in other.group.lower():  # VB skips restorer/auto groups
                continue
            buckets.setdefault(self.group_label(other.group), []).append(name)

        groups = [
            {"name": label, "mods": sorted(mods, key=key)}
            for label, mods in sorted(buckets.items(), key=lambda kv: key(kv[0]))
        ]
        return {
            "mod": mod_name,
            "groups": groups,
            "dependencies": sorted(md.dependencies, key=key),
        }

    def set_mod_dependencies(self, mod_name: str, deps: list[str]) -> dict:
        """Save a mod's dependency list + reconcile installs (VB ``BtSave_Click``).

        Persists the new dependency set. When the mod is installed, dependencies that
        were removed and are no longer required by any other installed mod are
        uninstalled, and newly-added dependencies that are not yet installed are
        installed (VB's automatic dependency reconciliation). Returns
        ``{"ok", "installed", "uninstalled", "message"}``.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {
                "ok": False,
                "installed": 0,
                "uninstalled": 0,
                "message": f"Unknown mod: {mod_name}",
            }

        old = set(md.dependencies)
        new = list(dict.fromkeys(deps))  # de-dupe, preserve order
        removed = [d for d in old if d not in new]
        md.dependencies = sorted(new, key=cmp_to_key(win_compare))
        self.save()

        uninstalled = installed = 0
        if md.installed:
            # Uninstall removed deps no longer needed by any other installed mod.
            uninstall_list = [
                d
                for d in removed
                if not any(
                    other.installed and d in other.dependencies
                    for oname, other in self.pd.mod_list.items()
                    if oname != mod_name
                )
            ]
            uninstall_list = [d for d in uninstall_list if self._mod_installed(d)]
            if uninstall_list:
                self.uninstall(uninstall_list)
                uninstalled = len(uninstall_list)
            # Install newly-added deps that are not installed.
            install_list = [d for d in new if not self._mod_installed(d)]
            if install_list:
                self.install(install_list)
                installed = len(install_list)

        return {
            "ok": True,
            "installed": installed,
            "uninstalled": uninstalled,
            "message": (
                f"Saved {len(new)} dependenc{'y' if len(new) == 1 else 'ies'} for {mod_name}."
            ),
        }

    def _mod_installed(self, mod_name: str) -> bool:
        md = self.pd.mod_item(mod_name)
        return md is not None and md.installed

    # -- File viewers (View menu) ----------------------------------------- #
    def nit_log_path(self) -> Path:
        """The application's own log file (VB NIT Log File)."""
        from vaultkeeper.core.log import log_file_path

        return log_file_path()

    def game_file_path(self, *parts: str) -> Path | None:
        """A file under the game user directory (logs/ini/settings), if known."""
        if self.ctx.game_user_dir is None:
            return None
        return self.ctx.game_user_dir.joinpath(*parts)

    def conflicts_report(self) -> dict:
        """Installed files claimed by more than one mod, with the winning installer.

        Surfaces the engine's last-by-``FileKeyInfo.Comparer`` winner selection (VB
        FileConflictsViewer): each row is a game file, the mod that currently owns it,
        and every mod whose installer maps onto it.
        """
        rows = []
        for ifd in self.pd.installed_list.values():
            if len(ifd.mod_file_conflicts) > 1:
                mods = sorted({mfk.mod_name for mfk in ifd.mod_file_conflicts})
                rows.append(
                    {
                        "file": ifd.key.file_key,
                        "winner": ifd.installer,
                        "mods": mods,
                        "count": len(mods),
                    }
                )
        rows.sort(key=lambda r: r["file"].lower())
        return {"rows": rows, "count": len(rows)}

    def game_saves_report(self) -> dict:
        """The current game saves as display rows plus totals (prompt-free).

        Also lists the current game's archived ranges (VB ``ArchivedFolder``) so the
        manager can offer Restore, and reports whether a Reduce is possible.
        """
        loop = self.play_loop
        if loop is None:
            return {
                "rows": [],
                "count": 0,
                "current": "",
                "total_size": "",
                "archived": [],
                "can_reduce": False,
            }
        gs = loop.game_saves()
        rows = [
            {
                "name": info.name,
                "save": info.game_save_name,
                "location": info.location,
                "type": info.save_type.name.title(),
                "size": _fmt_size(info.byte_size),
            }
            for info in gs.folders
        ]
        archived = self._archived_saves_rows(gs.current_game_save)
        # A Reduce needs at least one save beyond the newest one and the leading
        # quick/auto saves — mirror ArchiveGames' range check with keep=1.
        from vaultkeeper.game.save_archive import reduce_indices

        can_reduce = reduce_indices(gs.folders, 1) is not None
        return {
            "rows": rows,
            "count": gs.count,
            "current": gs.current_game_save,
            "total_size": _fmt_size(gs.total_size),
            "archived": archived,
            "can_reduce": can_reduce,
        }

    def archived_saves_root(self) -> Path:
        """The store's archived-game-saves folder (VB ``Paths.ArchivedSaves``)."""
        from vaultkeeper.game.save_archive import ARCHIVED_SAVES_SUBPATH

        return self.data_dir().parent.joinpath(*ARCHIVED_SAVES_SUBPATH)

    def _archived_saves_rows(self, game_name: str) -> list[dict]:
        """Display rows for the current game's archived ranges (VB ``ArchivedFolder``)."""
        from vaultkeeper.game.save_archive import scan_archived_ranges

        if not game_name:
            return []
        rows = []
        for rng in scan_archived_ranges(self.archived_saves_root(), game_name):
            rows.append(
                {
                    "range": rng.name,
                    "count": rng.saves.count,
                    "size": _fmt_size(rng.saves.total_size),
                }
            )
        return rows

    def reduce_game_saves(self, keep: int, *, on_existing: str = "overwrite") -> dict:
        """Archive the oldest active game saves (VB ``ArchiveGames`` / *Reduce*).

        Keeps the newest ``keep`` saves active and moves the rest into the archive.
        Returns ``{ok, moved, errors, range_name, message}``.
        """
        loop = self.play_loop
        if loop is None:
            return {"ok": False, "moved": 0, "message": "No game saves available."}
        from vaultkeeper.game.save_archive import archive_game_saves

        gs = loop.game_saves()
        result = archive_game_saves(
            gs, self.archived_saves_root(), keep=keep, on_existing=on_existing
        )
        return {
            "ok": result.ok,
            "moved": result.moved,
            "errors": result.errors,
            "range_name": result.range_name,
            "message": result.message,
        }

    def restore_archived_saves(self, range_name: str) -> dict:
        """Restore an archived range back to the live saves (VB ``RestoreGames``).

        Returns ``{ok, restored, errors, message}``.
        """
        loop = self.play_loop
        if loop is None:
            return {"ok": False, "restored": 0, "message": "No game saves available."}
        from vaultkeeper.game.save_archive import restore_game_saves

        game_name = loop.game_saves().current_game_save
        range_folder = self.archived_saves_root() / game_name / range_name
        result = restore_game_saves(range_folder, loop.saves_dir)
        return {
            "ok": result.ok,
            "restored": result.restored,
            "errors": result.errors,
            "message": result.message,
        }

    # -- Deactivate / Activate / Delete games (VB GameManager backup flows) -- #
    def game_backup_root(self) -> Path:
        """The store's deactivated-game backup folder (VB ``Paths.GameSaves``)."""
        from vaultkeeper.game.game_backup import GAME_SAVES_SUBPATH

        return self.data_dir().parent.joinpath(*GAME_SAVES_SUBPATH)

    def deactivated_games_report(self) -> dict:
        """The deactivated games held in the backup area + space totals (VB backup list).

        Returns ``{"games": [{name,count,size,size_bytes}], "backup_total",
        "backup_total_bytes"}`` — the second list of the two-list Game Saves Manager
        layout, plus the Backups space accounting (VB ``TotalBackupSize``).
        """
        from vaultkeeper.game.game_backup import scan_deactivated_games

        games = scan_deactivated_games(self.game_backup_root())
        rows = [
            {
                "name": g.name,
                "count": g.count,
                "size": _fmt_size(g.total_size),
                "size_bytes": g.total_size,
            }
            for g in games
        ]
        total = sum(g.total_size for g in games)
        return {
            "games": rows,
            "backup_total": _fmt_size(total),
            "backup_total_bytes": total,
        }

    def deactivate_current_game(self) -> dict:
        """Deactivate the active game into a backup (VB ``DeactivateGame``)."""
        loop = self.play_loop
        if loop is None:
            return {"ok": False, "moved": 0, "message": "No game saves available."}
        from vaultkeeper.game.game_backup import deactivate_game

        result = deactivate_game(
            loop.game_saves(), loop.saves_dir, self.game_backup_root()
        )
        return {"ok": result.ok, "moved": result.moved, "message": result.message}

    def activate_game(self, name: str) -> dict:
        """Activate a deactivated game, backing up the current one first (VB ``ActivateGame``)."""
        loop = self.play_loop
        if loop is None:
            return {"ok": False, "moved": 0, "message": "No game saves available."}
        from vaultkeeper.game.game_backup import activate_game

        backup_folder = self.game_backup_root() / name
        result = activate_game(
            backup_folder,
            loop.saves_dir,
            current_saves=loop.game_saves(),
            backup_root=self.game_backup_root(),
        )
        return {"ok": result.ok, "moved": result.moved, "message": result.message}

    def delete_game_backup(self, name: str, *, to_trash: bool = False) -> dict:
        """Delete a deactivated game's backup folder (VB ``DeleteGame``)."""
        from vaultkeeper.game.game_backup import delete_game_backup

        result = delete_game_backup(self.game_backup_root() / name, to_trash=to_trash)
        return {"ok": result.ok, "message": result.message}

    # -- Characters / portraits (VB BicFileInfo / CharacterViewer) --------- #
    def character_files(self) -> list:
        """The player's characters, from the local vault and each game save.

        VB's Character Explorer/Summary reads ``.bic`` files; the player's real
        characters live in ``localvault`` and one ``player.bic`` per game save.
        Returns a list of ``game.character.CharacterFile`` (each with decoded
        info, possibly invalid), local vault first then saves, name-sorted.
        """
        from vaultkeeper.game.character import scan_character_files

        user = self.ctx.game_user_dir
        if user is None:
            return []
        found = list(scan_character_files(user / "localvault"))
        saves = user / "saves"
        if saves.is_dir():
            for save_dir in sorted(saves.iterdir()):
                if save_dir.is_dir():
                    found.extend(scan_character_files(save_dir))
        return found

    def hak_portraits_root(self) -> Path:
        """NIT's folder for portraits extracted from haks (VB ``Paths.HakPortraits``)."""
        return self.data_dir().parent / "Backups" / "Portraits Extracted from Hak Files"

    def portrait_search_dirs(self) -> list[Path]:
        """NWN portrait search folders in priority order (VB PortraitDirectories)."""
        user = self.ctx.game_user_dir
        dirs: list[Path] = []
        if user is not None:
            if self.ctx.is_ee:
                dirs.append(user / "ovr")
            dirs.append(user / "override")
            dirs.append(user / "portraits")
        # Portraits extracted from haks (one subfolder per hak) are also searched.
        root = self.hak_portraits_root()
        if root.is_dir():
            dirs.extend(sorted(p for p in root.iterdir() if p.is_dir()))
        return dirs

    def extract_hak_portraits(self, hak_path: Path) -> dict:
        """Extract complete portrait sets from a hak into NIT's store (VB ExtractHakPortraits).

        Uses the native ERF reader (no external ERF utility). Extracted portraits
        land in ``<HakPortraits>/<hakname>`` and become searchable by the Portrait
        Manager. Returns ``{"count", "message"}``; a hak with no portraits leaves no
        folder behind.
        """
        from vaultkeeper.core.formats.erf_reader import ErfReader
        from vaultkeeper.game.character import extract_hak_portraits

        hak_path = Path(hak_path)
        dest = self.hak_portraits_root() / hak_path.name
        count = extract_hak_portraits(hak_path, dest, erf_reader=ErfReader())
        if count == 0:
            import shutil

            shutil.rmtree(dest, ignore_errors=True)
            return {
                "count": 0,
                "message": f"{hak_path.name} contains no portrait files.",
            }
        return {
            "count": count,
            "message": f"Extracted {count} portrait(s) from {hak_path.name}.",
        }

    def extract_mod_hak_portraits(self, mod_name: str) -> dict:
        """Extract portraits from every hak in a mod's installer (Portrait Manager helper).

        Convenience over :meth:`extract_hak_portraits`: the VB command runs per
        selected hak file; here we sweep the selected mod's installer ``hak`` folder.
        """
        from vaultkeeper.core import constants as C

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {"count": 0, "message": f"Unknown mod: {mod_name}"}
        hak_dir = self.ctx.profile_mods_dir / mod_name / C.MOD_INSTALLER_DIR / "hak"
        total = 0
        for hak in sorted(hak_dir.glob("*.hak")) if hak_dir.is_dir() else []:
            total += self.extract_hak_portraits(hak)["count"]
        return {
            "count": total,
            "message": f"Extracted {total} portrait(s) from {mod_name}'s haks.",
        }

    def clear_hak_portraits(self) -> dict:
        """Delete all hak-extracted portraits (VB MsClearHakPortraits)."""
        import shutil

        root = self.hak_portraits_root()
        existed = root.is_dir()
        if existed:
            shutil.rmtree(root, ignore_errors=True)
        return {
            "cleared": existed,
            "message": "Cleared extracted hak portraits."
            if existed
            else "No extracted hak portraits to clear.",
        }

    def portrait_path(self, resref: str, *, extra_dirs=()) -> Path | None:
        """Resolve a character's portrait TGA (``extra_dirs`` searched first)."""
        from vaultkeeper.game.character import resolve_portrait

        return resolve_portrait(resref, [*extra_dirs, *self.portrait_search_dirs()])

    def portrait_entries(self) -> list:
        """Installed portraits grouped by resref (VB Portrait Manager list)."""
        from vaultkeeper.game.character import scan_portraits

        return scan_portraits(self.portrait_search_dirs())

    # -- Start Screen / Loadscreens (VB StartScreenManager) ---------------- #
    def loadscreens_report(self) -> dict:
        """The managed NWN start-screen (loadscreen) images + which is active.

        Read-only view of VB ``StartScreenManager``: locates the NIT-managed
        loadscreen mod, lists its ``Loadscreen Images/*.tga`` files, and marks the
        active image (from ``StartscreenInfo.txt``) and any auto-excluded images.
        When the manager has never been set up (the mod does not exist) the report
        says so rather than inventing it. The add/install/slideshow actions are
        deferred.
        """
        from vaultkeeper.game import start_screen as ss

        md = self.pd.mod_item(ss.LOADSCREEN_MOD)
        if md is None:
            return {
                "exists": False,
                "mod_name": ss.LOADSCREEN_MOD,
                "installed": False,
                "active": "",
                "image_folder": "",
                "images": [],
                "count": 0,
                "excluded_count": 0,
                "prefix_enabled": False,
                "prefixed_count": 0,
                "summary": "NIT does not yet manage your NWN Start Screen.",
            }

        data_dir = self._profile_data_dir()
        image_folder = self.ctx.profile_mods_dir / md.mod_name / ss.SCREEN_FOLDER
        info = ss.read_start_screen_info(data_dir)
        active = info.active_screen if info is not None else ""
        excludes = ss.read_auto_excludes(data_dir)
        prefixes = ss.read_prefixes(data_dir)
        images = ss.scan_loadscreens(
            image_folder, active=active, excludes=excludes, prefixes=prefixes
        )
        installed = md.installed

        rows = [
            {
                "name": im.name,
                "path": str(im.path),
                "size": im.size,
                "size_text": _fmt_size(im.size),
                "excluded": im.excluded,
                "active": im.active,
                "prefixed": im.prefixed,
                "filter_prefixed": im.filter_prefixed,
            }
            for im in images
        ]
        excluded_count = sum(1 for im in images if im.excluded)
        prefixed_count = sum(1 for im in images if im.prefixed)

        # Summary line (VB InstalledStatusText tone): only an *installed* mod means
        # an image is actually the game's start screen right now.
        parts = [f"{len(rows)} loadscreen image{'' if len(rows) == 1 else 's'}"]
        if active:
            state = "installed" if installed else "selected (mod not installed)"
            parts.append(f"'{active}' {state}")
        elif installed:
            parts.append("NWN's Start Screen installed")
        if excluded_count:
            parts.append(f"{excluded_count} auto-excluded")
        if prefixes:  # VB SummaryInfo appends the prefixed count when PrefixEnabled.
            parts.append(f"{prefixed_count} prefixed")
        summary = " · ".join(parts) + "."

        return {
            "exists": True,
            "mod_name": md.mod_name,
            "installed": installed,
            "active": active,
            "image_folder": str(image_folder),
            "images": rows,
            "count": len(rows),
            "excluded_count": excluded_count,
            "prefix_enabled": bool(prefixes),
            "prefixed_count": prefixed_count,
            "summary": summary,
        }

    def add_loadscreen_exclusion(self, name: str) -> None:
        """Auto-exclude a loadscreen image from the slideshow (VB RbAddAutoExclusion).

        Appends the display name to the auto-exclusion list and persists it
        (VB ``SsInfo.AutoExcludes.Add`` + ``SaveAutoExcludes``).
        """
        from vaultkeeper.game import start_screen as ss

        data_dir = self._profile_data_dir()
        excludes = ss.read_auto_excludes(data_dir)
        excludes.append(name)
        ss.save_auto_excludes(data_dir, excludes)

    def remove_loadscreen_exclusion(self, name: str) -> None:
        """Un-exclude a loadscreen image (VB RbRemoveAutoExclusion).

        Removes the first case-insensitive match (VB ``FindItemIndex`` +
        ``RemoveAt``) and persists.
        """
        from vaultkeeper.game import start_screen as ss

        data_dir = self._profile_data_dir()
        excludes = ss.read_auto_excludes(data_dir)
        lower = name.lower()
        for i, existing in enumerate(excludes):
            if existing.lower() == lower:
                del excludes[i]
                break
        ss.save_auto_excludes(data_dir, excludes)

    def clear_loadscreen_exclusions(self) -> None:
        """Remove all auto-exclusions (VB RbInfoReport 'Remove Exclusions')."""
        from vaultkeeper.game import start_screen as ss

        ss.save_auto_excludes(self._profile_data_dir(), [])

    # -- Start Screen install engine (VB CreateLoadscreenInstaller/InstallLoadscreen) --
    def _loadscreen_image_folder(self, md: ModData) -> Path:
        """The managed mod's ``Loadscreen Images`` folder (VB ``ImageFolder``)."""
        from vaultkeeper.game import start_screen as ss

        return self.ctx.profile_mods_dir / md.mod_name / ss.SCREEN_FOLDER

    def ensure_loadscreen_mod(self) -> ModData:
        """Return the NIT-managed loadscreen mod, creating it if absent (VB AutoLoadscreen).

        The mod is created under the auto group (``Pdc.AutoGroup``) and its
        ``Loadscreen Images`` folder ensured, so images can be added to it.
        """
        from vaultkeeper.game import start_screen as ss

        md = self.pd.mod_item(ss.LOADSCREEN_MOD)
        if md is None:
            self.create_mod(ss.LOADSCREEN_MOD, ss.AUTO_GROUP)
            md = self.pd.mod_item(ss.LOADSCREEN_MOD)
        assert md is not None
        self._loadscreen_image_folder(md).mkdir(parents=True, exist_ok=True)
        return md

    def install_loadscreen(self, display_name: str) -> dict:
        """Install (or switch to) a loadscreen image as NWN's start screen.

        Faithful composite of VB ``CreateLoadscreenInstaller`` +
        ``InstallLoadscreen`` + the on-close active-screen update: copy the chosen
        image into the loadscreen mod's installer as
        ``override/gui_pre_bknd3.tga``, mark the mod an installer, install it (engine
        install + anneal → the file reaches the game ``override`` folder), then record
        it as the active start screen in ``StartscreenInfo.txt``. Returns
        ``{"ok", "message"}``.
        """
        from dataclasses import replace

        from vaultkeeper.core import constants as C
        from vaultkeeper.core import fs
        from vaultkeeper.game import start_screen as ss

        md = self.pd.mod_item(ss.LOADSCREEN_MOD)
        if md is None:
            return {"ok": False, "message": "NIT does not yet manage your NWN Start Screen."}
        image_file = self._loadscreen_image_folder(md) / display_name
        if not image_file.is_file():
            return {"ok": False, "message": f"Start screen image not found: {display_name}."}

        installer = self.ctx.profile_mods_dir / md.mod_name / C.MOD_INSTALLER_DIR
        dest = installer / ss.OVERRIDE_FOLDER / ss.NWN_START_SCREEN_NAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            fs.copy_file(image_file, dest, overwrite=True)
        except OSError:
            return {"ok": False, "message": "Unable to update Mod Installer."}

        # Register the override file + install the mod (copies it to the game override).
        self._create_identifier(md.mod_name, C.EXT_INSTALLER)
        self.install([md.mod_name])

        # Record the newly-installed image as the active start screen (VB on-close).
        data_dir = self._profile_data_dir()
        info = ss.read_start_screen_info(data_dir) or ss.StartScreenInfo(
            active_type="1", standard="", prefixed="", browse_folder=str(self.ctx.profile_mods_dir)
        )
        prefixes = ss.read_prefixes(data_dir)
        info = ss.with_active_screen(
            info, display_name, prefixed=ss.is_prefixed(display_name, prefixes)
        )
        info = replace(info, browse_folder=info.browse_folder or str(self.ctx.profile_mods_dir))
        ss.save_start_screen_info(data_dir, info)
        return {"ok": True, "message": f"Start Screen Installed: {display_name}."}

    def uninstall_loadscreen(self) -> dict:
        """Uninstall the loadscreen mod from the game (VB ``UninstallLoadscreenMod``).

        Runs the engine uninstall + anneal so ``gui_pre_bknd3.tga`` is removed from
        the game ``override`` folder. The active-screen name in ``StartscreenInfo.txt``
        is left to the caller (the Delete flow reselects the next image).
        """
        from vaultkeeper.game import start_screen as ss

        md = self.pd.mod_item(ss.LOADSCREEN_MOD)
        if md is None:
            return {"ok": False, "message": "NIT does not yet manage your NWN Start Screen."}
        self.uninstall([md.mod_name])
        return {"ok": True, "message": "Start Screen uninstalled."}

    # -- Start Screen add / delete images (VB ProcessFiles/ProcessFolders/RbDeleteFile) --
    def add_loadscreen_images(self, sources: list[Path], *, overwrite: bool = False) -> dict:
        """Copy image files into the managed mod's ``Loadscreen Images`` folder.

        Faithful port of VB ``ProcessFiles``: for each source the target name keeps
        the file name unless it is the reserved ``gui_pre_bknd3.tga`` (renamed from
        its folder, :func:`start_screen.add_image_target_name`). Files already present
        (or duplicated within the batch) are skipped unless ``overwrite`` is set. The
        managed mod is created if needed. Returns ``{"added", "skipped", "message"}``.
        """
        from vaultkeeper.core import fs
        from vaultkeeper.game import start_screen as ss

        md = self.ensure_loadscreen_mod()
        image_folder = self._loadscreen_image_folder(md)
        existing = {p.name.lower() for p in image_folder.glob("*") if p.is_file()}
        added = skipped = 0
        seen: set[str] = set()
        for source in sources:
            source = Path(source)
            if not source.is_file():
                continue
            target_name = ss.add_image_target_name(source.name, source.parent)
            lower = target_name.lower()
            if not overwrite and (lower in existing or lower in seen):
                skipped += 1
                continue
            seen.add(lower)
            try:
                fs.copy_file(source, image_folder / target_name, overwrite=True)
                added += 1
            except OSError:
                skipped += 1
        return {
            "added": added,
            "skipped": skipped,
            "message": f"Files added: {added or 'None'}. Skipped: {skipped or 'None'}.",
        }

    def add_loadscreen_folders(self, folders: list[Path], *, overwrite: bool = False) -> dict:
        """Add every ``.tga`` under the given folders (VB ``ProcessFolders`` + ``ProcessFiles``).

        Recurses each folder for loose ``.tga`` files and extracts nested archives
        (via the archive seam), filtering NWN's own GUI TGAs out of extracted content
        (:func:`start_screen.tga_file_exclusions`), then copies the result into the
        managed image folder.
        """
        import tempfile

        from vaultkeeper.game import start_screen as ss

        backend = self._archive_backend()
        with tempfile.TemporaryDirectory(prefix="vk-ls-folder-") as tmp:
            tmp_root = Path(tmp)
            counter = {"n": 0}

            def extract(archive: Path) -> Path | None:
                counter["n"] += 1
                dest = tmp_root / f"a{counter['n']}"
                result = backend.extract(archive, dest)
                return dest if result.ok else None

            files = ss.collect_tga_from_folders(
                folders, extract=extract, exclusions=ss.tga_file_exclusions()
            )
            return self.add_loadscreen_images(files, overwrite=overwrite)

    def add_loadscreen_from_hak(self, hak_path: Path, *, overwrite: bool = False) -> dict:
        """Extract the TGA resources from a ``.hak`` and add them (VB add-from-hak).

        Uses the ERF seam (``ErfReader.extract_all(hak, dest, res_type=3)``) to pull
        every TGA resource out of the hak, filters NWN's own GUI TGAs, then copies the
        result into the managed image folder.
        """
        import tempfile

        from vaultkeeper.core.formats.erf_reader import ErfReader
        from vaultkeeper.game import start_screen as ss

        hak_path = Path(hak_path)
        if not hak_path.is_file():
            return {"added": 0, "skipped": 0, "message": f"Hak not found: {hak_path.name}."}
        exclusions = ss.tga_file_exclusions()
        with tempfile.TemporaryDirectory(prefix="vk-ls-hak-") as tmp:
            extracted = ErfReader().extract_all(hak_path, Path(tmp), res_type=3)
            keep = [p for p in extracted if p.name.lower() not in exclusions]
            return self.add_loadscreen_images(keep, overwrite=overwrite)

    def delete_loadscreen_images(self, names: list[str]) -> dict:
        """Delete image files from the managed mod (VB ``RbDeleteFile`` @1340).

        Removes each named ``.tga`` from the ``Loadscreen Images`` folder, prunes any
        matching auto-exclusions, and — if the currently-active/installed image was
        deleted — uninstalls the loadscreen from the game and reselects the next
        available image as active (VB auto-select-next). Returns
        ``{"deleted", "message"}``.
        """
        from vaultkeeper.game import start_screen as ss

        md = self.pd.mod_item(ss.LOADSCREEN_MOD)
        if md is None:
            return {"deleted": 0, "message": "NIT does not yet manage your NWN Start Screen."}
        image_folder = self._loadscreen_image_folder(md)
        data_dir = self._profile_data_dir()
        info = ss.read_start_screen_info(data_dir)
        active = info.active_screen if info is not None else ""

        deleted = 0
        active_deleted = False
        for name in names:
            path = image_folder / name
            if path.is_file():
                path.unlink()
                deleted += 1
                if active and name.lower() == active.lower():
                    active_deleted = True

        if not deleted:
            return {"deleted": 0, "message": "No Start Screen images deleted."}

        # Prune auto-exclusions that no longer exist (VB ValidateAutoExcludes).
        remaining = {p.name.lower() for p in image_folder.glob("*.tga") if p.is_file()}
        excludes = [e for e in ss.read_auto_excludes(data_dir) if e.lower() in remaining]
        ss.save_auto_excludes(data_dir, excludes)

        # If the installed image was deleted it must be uninstalled; reselect the next.
        if active_deleted:
            self.uninstall_loadscreen()
            if info is not None:
                images = ss.scan_loadscreens(image_folder)
                next_name = images[0].name if images else ""
                if next_name:
                    prefixes = ss.read_prefixes(data_dir)
                    info = ss.with_active_screen(
                        info, next_name, prefixed=ss.is_prefixed(next_name, prefixes)
                    )
                else:
                    info = ss.cleared_active_screen(info)
                ss.save_start_screen_info(data_dir, info)

        return {
            "deleted": deleted,
            "message": f"Start Screen images deleted: {deleted}.",
        }

    def rename_loadscreen_image(
        self, old_name: str, new_name: str, *, replicate_vb_bug: bool = True
    ) -> dict:
        """Rename a loadscreen image (VB ``RbRename`` @1243) — **LANDMINE, see below**.

        Validates the new name (:func:`start_screen.validate_loadscreen_name`), renames
        the file in the ``Loadscreen Images`` folder, renames any matching
        auto-exclusion, and updates the active-screen slots in ``StartscreenInfo.txt``
        following VB's Standard/Prefixed reassignment branches.

        .. warning::
            VB has a genuine bug at StartScreenManager.vb:1271. When the *installed*
            image is renamed and its prefix-state is unchanged, VB executes
            ``SsInfo.Active = InstalledLoadScreen`` — writing the **display name** into
            the active-**type** slot (line 0 of the info file, which must hold ``"1"``
            or ``"2"``), corrupting ``StartscreenInfo.txt``. The clearly-intended code
            was ``SsInfo.ActiveScreen = InstalledLoadScreen`` (which writes the Standard
            or Prefixed name slot). We port the bug **faithfully by default**
            (``replicate_vb_bug=True``) so behaviour matches the original; pass
            ``replicate_vb_bug=False`` for the corrected behaviour. There is no real
            loadscreen data on this machine to validate against — flagged for review.

        Returns ``{"ok", "message"}``.
        """
        from dataclasses import replace

        from vaultkeeper.game import start_screen as ss

        md = self.pd.mod_item(ss.LOADSCREEN_MOD)
        if md is None:
            return {"ok": False, "message": "NIT does not yet manage your NWN Start Screen."}
        image_folder = self._loadscreen_image_folder(md)

        # Validate against the current display names (VB ValidateName existence check).
        pre = ss.scan_loadscreens(image_folder)
        existing = [im.name for im in pre]
        ok, value = ss.validate_loadscreen_name(
            new_name, initial=old_name, existing=existing
        )
        if not ok:
            return {"ok": False, "message": value}
        new_name = value

        src = image_folder / old_name
        if not src.is_file():
            return {"ok": False, "message": f"Rename of {old_name} failed."}

        data_dir = self._profile_data_dir()
        prefixes = ss.read_prefixes(data_dir)
        excludes = ss.read_auto_excludes(data_dir)

        # Available lists computed from the PRE-rename state (VB: RefreshScreenFiles
        # runs after the GetNextName calls, so ScreenFilenames still holds old names).
        exclude_lower = {e.lower() for e in excludes}
        standard_available = [n for n in existing if n.lower() not in exclude_lower]
        prefixed_available = [n for n in existing if ss.is_filter_prefixed(n, prefixes)]

        # Perform the file rename.
        try:
            src.rename(image_folder / new_name)
        except OSError:
            return {"ok": False, "message": f"Rename of {old_name} failed."}

        info = ss.read_start_screen_info(data_dir)
        if info is not None:
            new_prefixed = ss.is_prefixed(new_name, prefixes)
            old_prefixed = ss.is_prefixed(old_name, prefixes)
            installed = info.active_screen  # ~ VB InstalledLoadScreen

            if old_name == installed:  # case-sensitive (VB String.Compare CaseSensitive)
                if new_prefixed and not old_prefixed:
                    info = replace(
                        info,
                        standard=ss.get_next_name(standard_available, old_name),
                        prefixed=new_name,
                    )
                elif not new_prefixed and old_prefixed:
                    info = replace(
                        info,
                        prefixed=ss.get_next_name(prefixed_available, old_name),
                        standard=new_name,
                    )
                elif replicate_vb_bug:
                    # VB BUG @1271: writes a display name into the active-TYPE slot.
                    info = replace(info, active_type=new_name)
                else:
                    # Corrected: assign into the active screen name slot.
                    info = ss.with_active_screen(info, new_name, prefixed=new_prefixed)
            elif old_name == info.prefixed:
                if not new_prefixed and old_prefixed:
                    info = replace(
                        info, prefixed=ss.get_next_name(prefixed_available, old_name)
                    )
                else:
                    info = replace(info, prefixed=new_name)

            ss.save_start_screen_info(data_dir, info)

        # Rename the auto-exclusion entry (VB @1289: remove old, add new when neither
        # old nor new is prefixed — a prefixed image is auto-excluded elsewhere).
        if any(e.lower() == old_name.lower() for e in excludes):
            excludes = [e for e in excludes if e.lower() != old_name.lower()]
            if not ss.is_prefixed(new_name, prefixes) and not ss.is_prefixed(
                old_name, prefixes
            ):
                excludes.append(new_name)
            ss.save_auto_excludes(data_dir, excludes)

        return {"ok": True, "name": new_name, "message": f"Renamed to {new_name}"}

    def user_responses_report(self) -> dict:
        """The GameMapper's remembered user answers, grouped (VB UserResponseEditor).

        Four groups mirroring ``PopulateUserResponses``. Each row carries the
        ``key`` needed to delete it (mod name for Mod Choices, identifier else).
        """
        loop = self.play_loop
        if loop is None:
            return {"groups": []}
        uc = loop.game_mapper.user_choices

        def rows(mapping: dict) -> list[dict]:
            return [
                {"identifier": k, "mod_name": v, "key": k}
                for k, v in mapping.items()
            ]

        return {
            "groups": [
                {
                    "key": "mod_choices",
                    "title": "Mod Choices",
                    "rows": [
                        {"identifier": "N/A", "mod_name": m, "key": m}
                        for m in uc.mod_choices
                    ],
                },
                {"key": "log", "title": "Log to Mod Names", "rows": rows(uc.log_to_mod_names)},
                {
                    "key": "sav",
                    "title": "Game Save Name to Mod Names",
                    "rows": rows(uc.sav_to_mod_names),
                },
                {
                    "key": "profile",
                    "title": "Game Save Name to Profile Mod Names",
                    "rows": rows(uc.profile_choices),
                },
            ]
        }

    def delete_user_response(self, category: str, key: str) -> bool:
        """Forget a remembered GameMapper response (VB UserResponseEditor delete)."""
        loop = self.play_loop
        if loop is None:
            return False
        return loop.game_mapper.remove_user_response(category, key)

    def play_times_report(self) -> dict:
        """Per-mod play times (formatted, longest first) plus the NWN totals."""
        loop = self.play_loop
        if loop is None:
            return {"rows": [], "total_played": "", "most_in_one_day": "", "last_played": ""}
        pdm = loop.play_data
        rows = [
            {
                "mod": mod,
                "time": pdm.format_time(span, ""),
                "seconds": span.total_seconds(),
                "started": _fmt_date(pdm.start_date(mod)),
            }
            for mod, span in pdm.pdi.play_times.items()
        ]
        rows.sort(key=lambda r: r["seconds"], reverse=True)
        return {
            "rows": rows,
            "total_played": pdm.format_days(pdm.total_played, ""),
            "most_in_one_day": pdm.format_time(pdm.most_in_one_day, ""),
            "last_played": pdm.last_played,
        }

    def pending_play_report(self) -> dict:
        """Play-time records awaiting attribution to a mod (VB ``PlayDataViewPending``).

        The play loop records a completed session that GameMapper could not confirm
        against a mod as *pending* (``pending_play_times``); this surfaces those as
        rows ``{mod, completed, play_time, user}`` so the user can review them.
        Returns ``{"rows", "count"}``.
        """
        loop = self.play_loop
        if loop is None:
            return {"rows": [], "count": 0}
        rows = []
        for mod, records in loop.play_data.pending_play_times.items():
            for pti in records:
                rows.append(
                    {
                        "mod": mod,
                        "completed": pti.completed,
                        "play_time": pti.play_time,
                        "user": pti.user_name,
                    }
                )
        return {"rows": rows, "count": len(rows)}

    def mod_played_info(self, mod_name: str) -> str:
        """A short play-time summary for a mod (VB right-aligned ``MsPlayedInfo``).

        Returns e.g. ``"My Mod played for 3 hours 20 mins"`` or ``""`` when there is
        no play data / no selection. Read from the mod's total tracked play time.
        """
        loop = self.play_loop
        if loop is None or not mod_name:
            return ""
        pdm = loop.play_data
        span = pdm.pdi.play_times.get(mod_name)
        if span is None or span.total_seconds() <= 0:
            return ""
        return f"{mod_name} played for {pdm.format_time(span, '')}"

    def mod_play_report(self) -> dict:
        """Mods with a module file, oldest-completed first (VB ``ModPlayViewer``).

        Each row carries the current user's last completed date + play time, the
        mod's rating/levels/state, and its per-user play-time history, matching
        the VB ``ModPlayedInfo``. Rows sort by ``<completed> <mod name>`` using the
        Windows natural comparer (never-completed mods sort first, "from the
        oldest"). The group/rating/end-level/only-completed *filter options* are a
        deferred UI extension; this returns the full, unfiltered list.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.formatting import parse_date_string
        from vaultkeeper.core.win_sort import win_compare
        from vaultkeeper.game.play_data_manager import _current_user

        loop = self.play_loop
        pdm = loop.play_data if loop is not None else None
        user = _current_user()

        rows: list[dict] = []
        installed_count = 0
        for md in self.pd.mod_list.values():
            if not (md.is_not_group_item and md.has_mod_file):
                continue

            play_times: list[dict] = []
            completed = ""
            play_time = "None Recorded"
            if pdm is not None:
                records: list = []
                pdm.read_play_time_file(md.mod_name, records)
                play_times = [
                    {"completed": r.completed, "play_time": r.play_time, "user": r.user_name}
                    for r in records
                ]
                # The current user's record drives the Completed column and sort.
                for r in records:
                    if r.user_name == user:
                        completed = r.completed
                        play_time = r.play_time
                        break

            play_time = play_time.replace("hours", "hrs").replace("hour", "hr")

            sort_dt = parse_date_string(completed) or datetime.min
            sort_key = f"{sort_dt.strftime('%Y%m%d%H%M%S')} {md.mod_name}"

            if md.installed:
                installed_count += 1

            rows.append(
                {
                    "mod": md.mod_name,
                    "completed": completed,
                    "play_time": play_time,
                    "rating": md.rating.name.title(),
                    "start": _hyphen_if_negative(md.level_start),
                    "end": _hyphen_if_negative(md.level_end),
                    "state": int(md.mod_state),
                    "installed": md.installed,
                    "group": self.group_label(md.group),
                    "web_link": md.web_link,
                    "best_weapon": _to_weapon_text(md.best_weapon),
                    "played_info": self._time_since_played(md),
                    "notes": self.read_notes(md.mod_name),
                    "play_times": play_times,
                    "sort_key": sort_key,
                }
            )

        rows.sort(key=cmp_to_key(lambda a, b: win_compare(a["sort_key"], b["sort_key"])))
        total = len(rows)
        return {
            "rows": rows,
            "installed": installed_count,
            "total": total,
            "summary": f"{installed_count:,}/{total:,}",
        }

    def _time_since_played(self, md: ModData) -> str:
        """VB ``ModData.LastPlayed`` — time since last completed + play count."""
        if md.date_completed is None:
            return "No Play Time history recorded." if md.has_mod_file else ""
        diff = _date_diff_text(md.date_completed, datetime.now())
        nth = _ordinal(md.completed_count)
        if diff:
            return f"Played {diff} ago for the {nth} time."
        return f"Finished playing today for the {nth} time."

    def workshop_report(self) -> dict:
        """Steam Workshop subscriptions on disk, mapped to mods (VB ``WorkshopViewer``).

        Scans the Steam Workshop content folder for subscription id folders and
        marks each *managed* when a mod claims that workshop id. Returns rows
        (id / Yes-No / mod name), the content path, managed/unmanaged counts and a
        status line mirroring the VB summary. Empty when this isn't a Steam install.
        """
        from vaultkeeper.game.workshop import scan_workshop, workshop_content_path

        content = workshop_content_path(self.ctx.game_root)
        id_to_mod = {
            md.workshop_id: md.mod_name
            for md in self.pd.mod_list.values()
            if md.is_not_group_item and md.workshop_id
        }
        items = scan_workshop(content, id_to_mod) if content is not None else []
        rows = [
            {
                "id": it.id,
                "managed": "Yes" if it.managed else "No",
                "mod": it.mod_name,
                "folder": str(it.folder),
            }
            for it in items
        ]
        managed = sum(1 for it in items if it.managed)
        unmanaged = len(items) - managed
        return {
            "rows": rows,
            "content_path": str(content) if content is not None else "",
            "managed": managed,
            "unmanaged": unmanaged,
            "total": len(items),
            "summary": _workshop_summary(len(items), managed, unmanaged),
        }

    # -- Workshop contents diff/persistence (VB SteamWorkshop) ------------- #
    def _workshop_contents_file(self) -> Path:
        """The persisted WorkshopContents database (VB ``pd.SaveWorkshopContent``)."""
        return self._profile_data_dir() / "WorkshopContents.json"

    def _read_workshop_contents(self) -> dict:
        from vaultkeeper.game.workshop import contents_from_json
        from vaultkeeper.persistence.json_store import read_json

        return contents_from_json(read_json(self._workshop_contents_file(), default={}))

    def _save_workshop_contents(self, contents: dict) -> None:
        from vaultkeeper.game.workshop import contents_to_json
        from vaultkeeper.persistence.json_store import write_json

        path = self._workshop_contents_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, contents_to_json(contents))

    def workshop_refresh(self) -> dict:
        """Diff Steam's content against the stored database (VB ``ValidateSteamContent``).

        Detects newly-subscribed items, subscriptions whose files changed, and
        unsubscribed items (folders gone from Steam), persists the updated database,
        and returns ``{"added", "updated", "unsubscribed", "added_files",
        "updated_files", "removed_files", "summary"}`` (ids in the lists).
        """
        from vaultkeeper.game.workshop import diff_workshop, workshop_content_path

        content = workshop_content_path(self.ctx.game_root)
        stored = self._read_workshop_contents()
        if content is None:
            return {
                "added": [],
                "updated": [],
                "unsubscribed": list(stored),
                "added_files": 0,
                "updated_files": 0,
                "removed_files": 0,
                "summary": "This is not a Steam install.",
            }
        diff = diff_workshop(content, stored)
        self._save_workshop_contents(diff.contents)
        return {
            "added": diff.added,
            "updated": diff.updated,
            "unsubscribed": diff.unsubscribed,
            "added_files": diff.added_files,
            "updated_files": diff.updated_files,
            "removed_files": diff.removed_files,
            "summary": diff.summary,
        }

    def rename_workshop_mod(self, workshop_id: str, new_name: str) -> dict:
        """Rename a stored workshop subscription's mod name (VB ``RenameMod``)."""
        contents = self._read_workshop_contents()
        info = contents.get(workshop_id)
        if info is None:
            return {"ok": False, "message": f"Unknown workshop id: {workshop_id}"}
        info.mod_name = new_name
        self._save_workshop_contents(contents)
        return {"ok": True, "message": f"Renamed {workshop_id} to {new_name}."}

    def workshop_item_files(self, folder: str) -> list[dict]:
        """The files inside a workshop item's folder (the contents pane)."""
        base = Path(folder)
        if not base.is_dir():
            return []
        files: list[dict] = []
        for path in sorted(base.rglob("*")):
            if path.is_file():
                files.append(
                    {
                        "name": str(path.relative_to(base)),
                        "size": _fmt_size(path.stat().st_size),
                    }
                )
        return files

    def add_workshop_mod(
        self, workshop_id: str, *, build_installer: bool = True
    ) -> dict:
        """Add a Steam Workshop subscription as a NIT-managed mod (VB ``CreateModFolder``).

        Creates a mod folder under the Workshop group, links it to the Steam id +
        web page, and archives the subscription's content into the mod's
        ``_Workshop`` folder so the item survives an unsubscribe (VB
        ``UpdateWorkshopFile``). When ``build_installer`` is set (VB
        ``CreateInstallers``) the installer payload is built from that archive so the
        mod becomes installable. If a mod of the same name already exists, an existing
        *workshop* mod (one with a ``_Workshop`` folder) is re-linked to the id (VB
        ``CheckResubscribed``); an unrelated name clash is refused. Returns
        ``{"ok", "mod_name", "created", "archived", "installer", "message"}``.
        """
        from vaultkeeper.core import constants as C
        from vaultkeeper.game.workshop import (
            WORKSHOP_GROUP,
            resolve_mod_name,
            workshop_content_path,
            workshop_url,
        )

        def result(ok, mod_name, message, *, created=False, archived=False, installer=False):
            return {
                "ok": ok,
                "mod_name": mod_name,
                "created": created,
                "archived": archived,
                "installer": installer,
                "message": message,
            }

        content = workshop_content_path(self.ctx.game_root)
        if content is None:
            return result(False, "", "This is not a Steam install.")
        id_folder = content / workshop_id
        if not id_folder.is_dir():
            return result(False, "", f"Workshop item {workshop_id} is not subscribed.")

        mod_name = resolve_mod_name(id_folder, workshop_id)
        existing = self.pd.mod_item(mod_name)
        if existing is not None:
            if existing.workshop_id == workshop_id:
                return result(True, mod_name, f"{mod_name} is already managed.")
            mod_folder = self.ctx.profile_mods_dir / existing.mod_name
            if (mod_folder / C.WORKSHOP_DIR).is_dir():
                existing.workshop_id = workshop_id
                existing.web_link = workshop_url(workshop_id)
                self.save()
                return result(True, mod_name, f"Re-linked {mod_name} to Steam Workshop.")
            return result(False, mod_name, f"A mod named {mod_name} already exists.")

        # Create the mod under the Workshop group and link it to Steam.
        self.create_mod(mod_name, group=WORKSHOP_GROUP)
        md = self.pd.mod_item(mod_name)
        md.workshop_id = workshop_id
        md.web_link = workshop_url(workshop_id)
        self.save()

        # Archive the subscription content into the mod's _Workshop folder.
        archived = self._archive_workshop_item(mod_name, workshop_id, id_folder)

        installer = False
        if build_installer and archived:
            installer = self.build_installer_payload(mod_name).get("ok", False)

        return result(
            True,
            mod_name,
            f"Added {mod_name} from Steam Workshop.",
            created=True,
            archived=archived,
            installer=installer,
        )

    def _archive_workshop_item(
        self, mod_name: str, workshop_id: str, id_folder: Path
    ) -> bool:
        """Archive a subscription's files into the mod's ``_Workshop`` folder.

        Faithful to VB ``UpdateWorkshopFile`` — the archive is named after the
        subscription's display name and holds the id folder's contents at its root.
        Returns True when the archive was written (an empty subscription is skipped).
        """
        from vaultkeeper.core import constants as C
        from vaultkeeper.game.workshop import WorkshopIdInfo

        workshop_folder = self.ctx.profile_mods_dir / mod_name / C.WORKSHOP_DIR
        workshop_folder.mkdir(parents=True, exist_ok=True)
        display = WorkshopIdInfo(workshop_id, mod_name).display_name
        archive_path = workshop_folder / f"{display}.7z"
        # Store the id folder's contents at the archive root (VB "<IdFolder>\*").
        sources = [Path(p.name) for p in sorted(id_folder.iterdir())]
        if not sources:
            return False
        return self._archive_backend().create(
            archive_path, sources, base_dir=id_folder
        ).ok

    def doc_organiser_report(
        self,
        mod_names: list[str] | None = None,
        *,
        use_archives: bool = True,
        remove_version: bool = False,
    ) -> dict:
        """Documentation files in the given mods (VB ``DocOrganiser`` scan).

        For each mod (``mod_names`` or, when ``None``, all non-group mods) scans the
        mod root folder for documentation already present (**Contents**) and its
        ``_Downloads`` tree for candidate docs (**Downloads**), grounded on the VB
        doc-extension list. Each Downloads row carries its qualified ``doc_name``
        (VB ``DocInfo``), whether it should be copied (``copy``) and whether it is a
        CRC match of an existing Contents doc (``name_match``); Contents rows carry
        ``name_match`` too. Returns rows split into ``contents``/``downloads`` lists
        plus a status summary.

        The matching copy action is :meth:`copy_docs_to_mod`. When ``use_archives``
        is true the injected archive extractor is used to look inside ``_Downloads``
        archives (archive docs are described/matched but not copyable — see the
        method). ``remove_version`` mirrors the VB *Version* toggle (default off).
        """
        from vaultkeeper.game.documentation import scan_mod_docs

        if mod_names is None:
            mod_names = [
                md.mod_name
                for md in self.pd.mod_list.values()
                if md.is_not_group_item
            ]
        extractor = None
        if use_archives:
            backend = self._archive_backend()
            if getattr(backend, "available", False):
                extractor = backend

        rows: list[dict] = []
        scanned = 0
        for name in mod_names:
            md = self.pd.mod_item(name)
            if md is None or md.is_group_item:
                continue
            mod_folder = self.ctx.profile_mods_dir / name
            if not mod_folder.is_dir():
                continue
            scanned += 1
            from vaultkeeper.game.documentation import archive_source

            for entry in scan_mod_docs(
                name, mod_folder, extractor=extractor, remove_version=remove_version
            ):
                arc = archive_source(entry)
                rows.append(
                    {
                        "mod": entry.mod,
                        "file": entry.file_name,
                        "doc_name": entry.doc_name,
                        "folder": entry.folder,
                        "size": _fmt_size(entry.size),
                        "source": entry.source,
                        "copy": entry.copy,
                        "name_match": bool(entry.name_match),
                        "from_archive": entry.from_archive,
                        "source_path": str(entry.full_path),
                        # Recover the re-extraction source for archive docs (copyable now).
                        "archive": arc[0] if arc else "",
                        "inner": arc[1] if arc else "",
                    }
                )

        rows.sort(key=lambda r: (r["mod"].lower(), r["doc_name"].lower()))
        contents = [r for r in rows if r["source"] == "Contents"]
        downloads = [r for r in rows if r["source"] == "Downloads"]
        return {
            "rows": rows,
            "contents": contents,
            "downloads": downloads,
            "mods": scanned,
            "total": len(rows),
            "summary": _doc_summary(scanned, len(downloads), len(contents)),
        }

    def doc_preview(self, source_path: str) -> dict:
        """Preview text for a documentation file (VB ``DocOrganiser.DisplayFile``).

        Returns ``{"kind", "text"}``: ``kind="text"`` with the readable body for
        ``.txt``/``.rtf``/``.htm``/``.html`` (RTF is stripped to plain text via
        ``core/rtf``), ``kind="open_with"`` with a prompt for other formats (VB shows
        an *Open with …* link for ``.pdf``/``.doc`` etc.), or ``kind="missing"`` when
        the file is gone (e.g. an archive-extracted doc whose temp copy was removed).
        """
        from vaultkeeper.core.rtf import read_rtf_text

        path = Path(source_path)
        if not source_path or not path.is_file():
            return {"kind": "missing", "text": ""}
        ext = path.suffix.lower()
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"kind": "missing", "text": ""}
        if ext == ".rtf":
            return {"kind": "text", "text": read_rtf_text(raw)}
        if ext in (".txt", ".htm", ".html"):
            return {"kind": "text", "text": raw}
        return {
            "kind": "open_with",
            "text": f"Open with the application associated with {ext} files.",
        }

    def copy_docs_to_mod(self, mod_name: str, selections: list[dict]) -> dict:
        """Copy chosen Downloads docs into the mod root (VB ``BtCopy_Click``).

        ``selections`` is a list of ``{"source": <path>, "doc_name": <target name>}``
        entries — typically the checked Downloads rows from
        :meth:`doc_organiser_report`. Each source file is copied into the mod's
        **root** folder (``ModData.ModPath`` — *not* ``.Mod Installer``) under its
        qualified ``doc_name``, overwriting any existing file (VB
        ``FS.CopyFile(..., IOAction.Overwrite)``). Docs are not tracked installer
        files, so the profile database is left untouched (VB only reloads the
        Contents view). Returns ``{"copied", "errors", "message"}``.

        A selection for a doc *inside* a ``_Downloads`` archive carries
        ``{"archive": <mod-relative archive>, "inner": <path in archive>, "doc_name"}``
        instead of a loose ``source``; the archive is re-extracted (via the injected
        extractor) and just that doc copied out (VB re-uses its persistent
        ``ExtractedZips``). Missing sources are counted as errors.
        """
        import contextlib

        from vaultkeeper.core import fs

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {"copied": 0, "errors": 0, "message": f"Unknown mod: {mod_name}"}
        target_folder = self.ctx.profile_mods_dir / mod_name
        if not target_folder.is_dir():
            return {
                "copied": 0,
                "errors": 0,
                "message": f"Mod folder missing: {mod_name}",
            }

        copied = errors = 0
        # Re-extract each needed archive once, caching its temp dir for the batch.
        extracted: dict[str, Path | None] = {}
        stack = contextlib.ExitStack()
        with stack:
            for sel in selections:
                doc_name = sel.get("doc_name")
                if not doc_name:
                    errors += 1
                    continue
                if sel.get("archive"):
                    source = self._extracted_doc_source(
                        target_folder, sel, extracted, stack
                    )
                else:
                    source = Path(sel["source"])
                if source is None or not source.is_file():
                    errors += 1
                    continue
                try:
                    fs.copy_file(source, target_folder / doc_name, overwrite=True)
                    copied += 1
                except OSError:
                    errors += 1

        return {
            "copied": copied,
            "errors": errors,
            "message": _doc_copy_summary(copied, errors),
        }

    def _extracted_doc_source(
        self, mod_folder: Path, sel: dict, extracted: dict, stack
    ) -> Path | None:
        """Re-extract a ``_Downloads`` archive (once, cached) and locate a doc in it.

        Returns the extracted file's path (``<temp>/<inner>``, falling back to a
        recursive name match) or ``None`` if the archive can't be extracted / the
        doc isn't found. ``extracted`` caches temp dirs per archive across the batch.
        """
        import tempfile

        archive_rel = sel["archive"]
        if archive_rel not in extracted:
            archive_path = mod_folder / archive_rel
            backend = self._archive_backend()
            if not (archive_path.is_file() and getattr(backend, "available", False)):
                extracted[archive_rel] = None
            else:
                tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))
                result = backend.extract(archive_path, tmp)
                extracted[archive_rel] = tmp if result.ok else None
        temp_root = extracted[archive_rel]
        if temp_root is None:
            return None
        candidate = temp_root / sel["inner"]
        if candidate.is_file():
            return candidate
        name = Path(sel["inner"]).name
        return next((p for p in temp_root.rglob(name) if p.is_file()), None)

    def wizard_report(self, mod_name: str) -> dict:
        """The installer wizard defined for a mod (VB ``WizardBuilder``/``WizardInfo``).

        Reads the mod's ``.Installer Wizard.nitwiz`` into a data view: title, the
        extract-archives flag, the SelectOne *choices*, the SelectMany *preferences*
        (with default checked state) and the InstallerExcludes list. ``has_wizard``
        is false when no wizard file exists. Read-only — the authoring/build action
        (Save/Delete, validation against the mod's real files) is deferred.
        """
        from vaultkeeper.game.wizard import load_wizard

        md = self.pd.mod_item(mod_name)
        title = mod_name
        info = None
        if md is not None and not md.is_group_item:
            mod_folder = self.ctx.profile_mods_dir / mod_name
            info = load_wizard(mod_folder, mod_name)

        if info is None:
            return {
                "mod": mod_name,
                "has_wizard": False,
                "title": f"{mod_name} Installer Wizard" if mod_name else "",
                "extract_archives": False,
                "select_one_text": "",
                "select_many_text": "",
                "choices": [],
                "preferences": [],
                "excludes": [],
                "run_wizard": False,
                "summary": f"No installer wizard defined for {title}.",
            }

        choices = [
            {"key": key, "display": display}
            for key, display in info.select_one.items()
        ]
        preferences = [
            {"key": p.key, "display": p.display, "checked": p.checked}
            for p in info.select_many
        ]
        return {
            "mod": mod_name,
            "has_wizard": True,
            "title": info.title,
            "extract_archives": info.extract_archives,
            "select_one_text": info.select_one_text,
            "select_many_text": info.select_many_text,
            "choices": choices,
            "preferences": preferences,
            "excludes": list(info.installer_excludes),
            "run_wizard": info.run_wizard,
            "summary": _wizard_summary(
                len(choices), len(preferences), len(info.installer_excludes)
            ),
        }

    def _scan_wizard_sources(self, mod_folder: Path):
        """Scan a mod's real files for wizard validation (VB ``ScanFiles`` wiring)."""
        from vaultkeeper.game.wizard import scan_mod_files

        mapper = self.ctx.mapper
        return scan_mod_files(
            mod_folder,
            is_installable=lambda p: mapper.get_mapped_folder(p, erf_check=True) != "",
            is_excluded_folder=mapper.is_excluded_folder,
        )

    def validate_wizard(
        self, mod_name: str, *, save: bool = False, extract: bool | None = None
    ) -> dict:
        """Prune a wizard's dead entries against the mod's real files (VB ``Validate``).

        Loads the mod's wizard, scans its actual files, and removes SelectOne /
        SelectMany / InstallerExcludes entries that no longer point at a real file.
        By default this is in-memory only (VB ``Validate``); pass ``save=True`` to
        persist the cleaned wizard. If a duplicate file/archive name is found the scan
        is suppressed (VB ``SuppressWizardCreation``) and nothing is pruned. Returns
        ``{ok, has_wizard, removed, saved, suppressed, duplicate, message}``.

        Archives are extracted (VB ``ProcessArchive``) so entries referencing files
        *inside* an archive resolve correctly, matching VB's rule of extracting when
        the wizard's ``ExtractArchives`` flag is on. Pass ``extract=True``/``False`` to
        force the extract pass on/off (VB ``Validate``'s ``extract`` argument);
        ``None`` (default) follows the wizard's ``ExtractArchives`` flag.
        """
        from vaultkeeper.game.wizard import load_wizard, save_wizard, validate

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return _wizard_op_result(False, message=f"Unknown mod: {mod_name}")
        mod_folder = self.ctx.profile_mods_dir / mod_name
        info = load_wizard(mod_folder, mod_name)
        if info is None:
            return _wizard_op_result(
                True,
                has_wizard=False,
                message=f"No installer wizard defined for {mod_name}.",
            )

        scan = self._scan_wizard_sources(mod_folder)
        if scan.suppressed:
            return _wizard_op_result(
                False,
                has_wizard=True,
                suppressed=True,
                duplicate=scan.duplicate,
                message=(
                    f"Duplicate file detected: {scan.duplicate}. "
                    "Resolve it before validating the wizard."
                ),
            )

        do_extract = info.extract_archives if extract is None else extract
        if do_extract and scan.archives:
            from vaultkeeper.game.wizard import extract_archives

            mapper = self.ctx.mapper
            info.extracted_archives = extract_archives(
                scan,
                extractor=self._archive_backend(),
                is_installable=lambda p: mapper.get_mapped_folder(p, erf_check=True)
                != "",
            )

        removed = validate(info, scan.source_files)
        saved = save_wizard(mod_folder, info) if (save and removed) else False
        return _wizard_op_result(
            True,
            has_wizard=True,
            removed=removed,
            saved=saved,
            message=_wizard_validate_message(removed, saved),
        )

    def delete_wizard(self, mod_name: str, *, to_trash: bool = False) -> dict:
        """Delete a mod's installer wizard file (VB ``Delete``).

        Pass ``to_trash=True`` to honour the recycle-bin preference (the window holds
        the ``recycle_on_delete`` setting; VB uses ``ui.Recycle``). Returns
        ``{ok, message}``.
        """
        from vaultkeeper.game.wizard import delete_wizard

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {"ok": False, "message": f"Unknown mod: {mod_name}"}
        mod_folder = self.ctx.profile_mods_dir / mod_name
        removed = delete_wizard(mod_folder, to_trash=to_trash)
        if removed:
            return {"ok": True, "message": f"Deleted the installer wizard for {mod_name}."}
        return {
            "ok": False,
            "message": f"No installer wizard to delete for {mod_name}.",
        }

    def wizard_source_files(self, mod_name: str) -> list[str]:
        """Eligible installer files for wizard authoring (VB ``PopulateFiles``/``RefreshFiles``).

        Scans the mod's real files through the installer's mapping predicate and
        returns the Windows-sorted relative-path keys — the *source list* the user
        transfers into the Choices / Preferences / Exclude lists. Bounded: this is the
        loose-file view (VB ``ExtractType.Files``); the archive-extraction views
        (Folders / FolderFiles) are not surfaced.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return []
        mod_folder = self.ctx.profile_mods_dir / mod_name
        result = self._scan_wizard_sources(mod_folder)
        return sorted(result.source_files.keys(), key=cmp_to_key(win_compare))

    def save_wizard_authoring(
        self,
        mod_name: str,
        *,
        title: str,
        select_one_text: str,
        select_many_text: str,
        choices: list[dict],
        preferences: list[dict],
        excludes: list[str],
        extract_archives: bool = False,
    ) -> dict:
        """Build + save a wizard from the authoring UI (VB ``BtSave_Click``).

        ``choices`` / ``preferences`` are ``{"key", "display"[, "checked"]}`` rows;
        ``excludes`` is a list of relative-path keys. SelectOne/SelectMany are sorted
        by display name (VB ``SortedDictionary(WindowsSorter)``). ``extract_archives``
        carries the flag through (VB recomputes it from ``IsExtractedFile`` after the
        extract pass; the bounded loose-file port carries the loaded value). Returns
        ``{"ok", "message"}``.
        """
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare
        from vaultkeeper.game.wizard import (
            WizardInfo,
            WizardPreference,
            save_wizard,
        )

        md = self.pd.mod_item(mod_name)
        if md is None or md.is_group_item:
            return {"ok": False, "message": f"Unknown mod: {mod_name}"}
        mod_folder = self.ctx.profile_mods_dir / mod_name

        info = WizardInfo(
            mod_name=mod_name,
            title_value=title.strip(),
            extract_archives=extract_archives,
            select_one_text_value=select_one_text.strip(),
            select_many_text_value=select_many_text.strip(),
        )
        by_display = cmp_to_key(lambda a, b: win_compare(a["display"], b["display"]))
        for choice in sorted(choices, key=by_display):
            info.select_one[choice["key"]] = choice["display"]
        for pref in sorted(preferences, key=by_display):
            info.select_many.append(
                WizardPreference(
                    key=pref["key"],
                    display=pref["display"],
                    checked=bool(pref.get("checked", True)),
                )
            )
        info.installer_excludes = list(excludes)

        if save_wizard(mod_folder, info):
            self._create_identifier_refresh(mod_name)
            return {"ok": True, "message": f"Installer wizard saved for {mod_name}."}
        return {"ok": False, "message": "Unable to save the installer wizard."}

    def _create_identifier_refresh(self, mod_name: str) -> None:
        """Rescan a mod's files after writing the wizard (VB FvContents.Reload)."""
        md = self.pd.mod_item(mod_name)
        if md is not None and not md.is_group_item:
            self.pd.scan_mod_files(md, self.ctx.profile_mods_dir)
            self.save()

    def locations_report(self) -> dict:
        """The resolved file locations for this profile/install (VB Settings Locations).

        Groups the real paths Vaultkeeper is using — the Neverwinter Nights install,
        the game user folder and Steam Workshop content, plus the tool's own profile
        mods folder and data store — as (group / location / path) rows for the
        Settings *Locations* page (columns ``Location`` / ``Path``). Read-only.
        """
        from vaultkeeper.game.workshop import workshop_content_path

        ctx = self.ctx
        workshop = workshop_content_path(ctx.game_root)
        store_root = self.store_path.parent if self.store_path else None
        groups: list[tuple[str, list[tuple[str, Path | None]]]] = [
            (
                "Neverwinter Nights",
                [
                    ("Game Installation", ctx.game_root),
                    ("Game User Folder", ctx.game_user_dir),
                    ("Steam Workshop Content", workshop),
                ],
            ),
            (
                "Vaultkeeper",
                [
                    ("Profile Mods", ctx.profile_mods_dir),
                    ("Data Store", store_root),
                    ("Profile Store File", self.store_path),
                ],
            ),
        ]
        rows = [
            {
                "group": group,
                "location": name,
                "path": str(path) if path is not None else "",
            }
            for group, items in groups
            for name, path in items
        ]
        set_count = sum(1 for r in rows if r["path"])
        return {
            "rows": rows,
            "summary": f"Locations: {set_count} of {len(rows)} resolved.",
        }

    def folder_mapping_report(self) -> dict:
        """The Mapper's folder-mapping tables (VB Settings Map Extensions/Files/Folders).

        Surfaces the read-only mapping rules that decide where a mod file installs:
        the extension map (Extension / Default Folder / Secondary Folder), the
        exception-file map (File Name / NWN Folder) and the directory map (Source
        Folder / NWN Folder). Grounded on ``core/mapper.py`` (the tested v21 tables).
        The Settings editing surface (add/rename/reset/import, persistence) is deferred.
        """
        mapper = self.ctx.mapper
        extensions = [
            {
                "ext": ext,
                "folder": folder,
                "secondary": mapper.folder_moves.get(ext, ""),
                "override": mapper.is_override("ext_mapping", ext),
            }
            for ext, folder in sorted(mapper.ext_mapping.items())
        ]
        files = [
            {
                "file": name,
                "folder": folder,
                "override": mapper.is_override("exception_files", name),
            }
            for name, folder in sorted(mapper.exception_files.items())
        ]
        folders = [
            {
                "source": source,
                "folder": folder,
                "override": mapper.is_override("dir_mapping", source),
            }
            for source, folder in sorted(mapper.dir_mapping.items())
        ]
        return {
            "extensions": extensions,
            "files": files,
            "folders": folders,
            "summary": (
                f"Extensions: {len(extensions)}. Map files: {len(files)}. "
                f"Map folders: {len(folders)}."
            ),
        }

    # -- Map editing + persistence (VB Settings map editors, Phase 8) ------ #
    def _persist_map_overrides(self) -> None:
        from vaultkeeper.config.settings import load_settings, save_settings

        settings = load_settings(self._settings_path)
        settings.map_overrides = self.ctx.mapper.export_overrides()
        settings.map_exclude_overrides = self.ctx.mapper.export_exclude_overrides()
        save_settings(settings, self._settings_path)

    def map_excludes_report(self) -> dict:
        """The Mapper's exclude lists, flagging user additions (VB "Excluded Items").

        ``files`` and ``folders`` are ``[{"name", "override"}, ...]`` — the file
        names / folder names the installer scan skips (``is_excluded_file`` /
        ``is_excluded_folder``); ``override`` marks a user addition (removable).
        """
        mapper = self.ctx.mapper
        files = [
            {"name": name, "override": mapper.is_exclude_override("files", name)}
            for name in sorted(mapper.exclude_files)
        ]
        folders = [
            {"name": name, "override": mapper.is_exclude_override("folders", name)}
            for name in sorted(mapper.exclude_folders)
        ]
        return {
            "files": files,
            "folders": folders,
            "summary": f"Excluded files: {len(files)}. Excluded folders: {len(folders)}.",
        }

    def add_map_exclude(self, kind: str, name: str) -> None:
        """Add a user exclude (``kind`` = ``"files"``/``"folders"``) and persist."""
        self.ctx.mapper.add_exclude(kind, name)
        self._persist_map_overrides()

    def remove_map_exclude(self, kind: str, name: str) -> bool:
        """Remove a user-added exclude and persist. Defaults are not removable."""
        removed = self.ctx.mapper.remove_exclude(kind, name)
        if removed:
            self._persist_map_overrides()
        return removed

    def set_map_extension(self, extension: str, folder: str) -> None:
        """Override an extension's default install folder and persist it."""
        ext = extension if extension.startswith(".") else f".{extension}"
        self.ctx.mapper.set_override("ext_mapping", ext, folder)
        self._persist_map_overrides()

    def set_map_file_exception(self, filename: str, folder: str) -> None:
        """Add/replace a file-name → folder exception and persist it."""
        self.ctx.mapper.set_override("exception_files", filename, folder)
        self._persist_map_overrides()

    def set_map_folder(self, source: str, folder: str) -> None:
        """Add/replace a source-folder → NWN-folder mapping and persist it."""
        self.ctx.mapper.set_override("dir_mapping", source, folder)
        self._persist_map_overrides()

    def remove_map_override(self, table: str, key: str) -> bool:
        """Remove a user-added map override (extension/file/folder) and persist."""
        removed = self.ctx.mapper.remove_override(table, key)
        if removed:
            self._persist_map_overrides()
        return removed

    def reset_map_overrides(self) -> None:
        """Discard all map customisations, restoring the default tables; persist."""
        self.ctx.mapper.reset_overrides()
        self._persist_map_overrides()

    def save(self) -> None:
        if self.store_path is not None:
            save_profile(self.pd, self.store_path)

    def counts(self) -> tuple[int, int]:
        """(total mods, installed mods)."""
        total = len(self.pd.mod_keys)
        installed = sum(
            1 for n in self.pd.mod_keys if (m := self.pd.mod_item(n)) and m.installed
        )
        return total, installed

    # -- Config-isolation guard ------------------------------------------- #
    def _config_guard(self) -> ConfigGuard | None:
        if self.ctx.game_user_dir is None:
            return None
        snapshot = config_root() / "game_config_snapshot.json"
        return ConfigGuard(self.ctx.game_user_dir, snapshot_path=snapshot)

    def game_config_changes(self) -> list[ConfigChange]:
        """Game config files changed since the accepted baseline (read-only)."""
        guard = self._config_guard()
        return guard.check() if guard is not None else []

    def accept_game_config(self) -> None:
        """Record the current game config as the baseline (writes only VK's snapshot)."""
        guard = self._config_guard()
        if guard is not None:
            guard.accept()

    def startup_config_check(self) -> list[ConfigChange]:
        """First run establishes the baseline quietly; later runs report real drift."""
        guard = self._config_guard()
        if guard is None:
            return []
        if not guard.has_baseline():
            guard.accept()
            return []
        return guard.check()


def _fmt_date(value: datetime | None) -> str:
    """Format an optional start date as ``dd MMM yyyy`` (blank when unset)."""
    from vaultkeeper.core.formatting import to_date_string

    return to_date_string(value) if value is not None else ""


def _workshop_summary(total: int, managed: int, unmanaged: int) -> str:
    """VB ``WorkshopViewer.PopulateWorkshop`` status line."""
    if total == 0:
        return "Steam Workshop Subscriptions detected: None."
    parts = [f"Workshop Subscriptions: {total:,}."]
    if managed > 0:
        parts.append(" Managed: " + ("All." if unmanaged == 0 else f"{managed:,}."))
    if unmanaged > 0:
        parts.append(" Unmanaged: " + ("All." if managed == 0 else f"{unmanaged:,}."))
    return "".join(parts)


def _doc_summary(mods: int, downloads: int, contents: int) -> str:
    """Status line for the Documentation Organiser (VB ``FilesToCopy`` display).

    Mirrors the VB counts: how many downloadable documents were detected and how
    many docs are already present in the Contents panel, across the mods scanned.
    """
    if mods == 0:
        return "No eligible mods selected."
    mod_text = "1 mod" if mods == 1 else f"{mods:,} mods"
    down = "None" if downloads == 0 else f"{downloads:,}"
    cont = "None" if contents == 0 else f"{contents:,}"
    return (
        f"Scanned {mod_text}. Downloaded documents detected: {down}. "
        f"Documents in Contents: {cont}."
    )


def _doc_copy_summary(copied: int, errors: int) -> str:
    """Status line after a doc copy (VB ``DocOrganiser.InfoText``)."""
    copied_text = "None" if copied == 0 else f"{copied:,}"
    if errors == 0:
        return f"Documents copied: {copied_text}."
    return f"Documents copied: {copied_text}. Errors: {errors:,}."


def _publish_result(
    ok: bool, *, path: str = "", zip_name: str = "", message: str = ""
) -> dict:
    """Assemble a publish-op result dict (VB PublishMod outcome)."""
    return {"ok": ok, "path": path, "zip_name": zip_name, "message": message}


def _wizard_op_result(
    ok: bool,
    *,
    has_wizard: bool = False,
    removed: int = 0,
    saved: bool = False,
    suppressed: bool = False,
    duplicate: str = "",
    message: str = "",
) -> dict:
    """Assemble a wizard authoring-op result dict (validate/delete)."""
    return {
        "ok": ok,
        "has_wizard": has_wizard,
        "removed": removed,
        "saved": saved,
        "suppressed": suppressed,
        "duplicate": duplicate,
        "message": message,
    }


def _wizard_validate_message(removed: int, saved: bool) -> str:
    """Status line after validating a wizard (VB ``Validate`` outcome)."""
    if removed == 0:
        return "All installer wizard entries point to existing files."
    entries = "entry" if removed == 1 else "entries"
    tail = " Saved." if saved else ""
    return f"Removed {removed:,} wizard {entries} with no matching file.{tail}"


def _wizard_summary(choices: int, preferences: int, excludes: int) -> str:
    """Status line describing a wizard's contents (VB WizardBuilder status)."""
    parts = [
        f"Choices: {choices}",
        f"Preferences: {preferences}",
        f"Installer excludes: {excludes}",
    ]
    return ". ".join(parts) + "."


def _hyphen_if_negative(value: int) -> str:
    """VB ``ToHyphenIfNegative`` — a hyphen for unset (negative) level values."""
    return "-" if value < 0 else str(value)


def _to_weapon_text(weapon) -> str:
    """VB ``ToWeaponText`` — ``Long_Sword`` -> ``Long Sword``, TwoBladed -> Two-Bladed."""
    return weapon.name.replace("_", " ").title().replace("Twobladed", "Two-Bladed")


def _ordinal(n: int) -> str:
    """``1`` -> ``1st``, ``2`` -> ``2nd`` … (VB ``ToSuffixedNumber``)."""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _date_diff_text(start: datetime, end: datetime) -> str:
    """Years/months/days between two dates (empty when same day; VB ToDateDiffText)."""
    import calendar

    if end.date() <= start.date():
        return ""
    years = end.year - start.year
    months = end.month - start.month
    days = end.day - start.day
    if days < 0:
        months -= 1
        prev_month = end.month - 1 or 12
        prev_year = end.year if end.month > 1 else end.year - 1
        days += calendar.monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    return " ".join(parts)


def _fmt_size(byte_size: int) -> str:
    """Human-readable byte size (B / KB / MB / GB)."""
    if byte_size < 0:
        return ""
    size = float(byte_size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} GB"
