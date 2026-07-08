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
from vaultkeeper.persistence.profile_store import load_profile, save_profile
from vaultkeeper.ui.play_loop import PlayLoop


class ProfileController:
    """Owns the active profile and drives install/uninstall/save."""

    def __init__(
        self,
        pd: ProfileData,
        ctx: InstallContext,
        *,
        store_path: Path | None = None,
    ) -> None:
        self.pd = pd
        self.ctx = ctx
        self.store_path = store_path
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

    # -- Construction ------------------------------------------------------ #
    @classmethod
    def open_profile(
        cls,
        *,
        profile_mods_dir: Path,
        game_root: Path,
        store_path: Path | None = None,
        is_ee: bool = True,
    ) -> ProfileController:
        """Load a profile from ``store_path`` (or scan from disk if absent), wire it up."""
        mapper = Mapper(is_ee=is_ee)
        game_folders = mapper.nwn_folder_paths(game_root)
        game_user_dir = user_documents_dir(HostOS.current())

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

        ctx = InstallContext(
            profile_mods_dir=profile_mods_dir,
            game_root=game_root,
            game_folders=game_folders,
            root_folder_name=game_root.name,
            mapper=mapper,
            is_ee=is_ee,
            game_user_dir=game_user_dir,
        )
        return cls(pd, ctx, store_path=store_path)

    # -- Queries ----------------------------------------------------------- #
    def groups(self) -> list[tuple[str, list[ModData]]]:
        """Return (group_name, member mods) pairs, groups and members natural-sorted."""
        from functools import cmp_to_key

        from vaultkeeper.core.win_sort import win_compare

        by_group: dict[str, list[ModData]] = {}
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

    # -- Operations -------------------------------------------------------- #
    def install(self, names: list[str]) -> str:
        self.engine.install_files(self.mod_files(names), anneal_mods=names)
        return self.engine.result_message

    def uninstall(self, names: list[str]) -> str:
        self.engine.uninstall_files(self.mod_files(names), anneal_mods=names)
        return self.engine.result_message

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

    def calculate_crcs(self) -> str:
        """Recompute CRC-32 checksums for pending files and refresh states."""
        self.pd.calculate_checksums(self.ctx.profile_mods_dir, self.ctx.game_folders)
        self.pd.update_file_states()
        self.pd.update_mod_states()
        self.save()
        return "CRC calculation complete."

    def rebuild_database(self) -> str:
        """Rebuild the profile database from disk (VB Rebuild Database)."""
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

    def download_project(self, files: list, mod_name: str, *, on_progress=None) -> list:
        """Download the given files into ``mod_name``'s ``_Downloads`` folder."""
        from vaultkeeper.core import constants as C
        from vaultkeeper.vault.downloader import Downloader

        dest = self.ctx.profile_mods_dir / mod_name / C.DOWNLOADS_DIR
        downloader = Downloader(
            self._http, scraper=self._make_scraper(), on_progress=on_progress
        )
        return downloader.download_all(files, dest)

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
                    "group": md.group,
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
        """The current game saves as display rows plus totals (prompt-free)."""
        loop = self.play_loop
        if loop is None:
            return {"rows": [], "count": 0, "current": "", "total_size": ""}
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
        return {
            "rows": rows,
            "count": gs.count,
            "current": gs.current_game_save,
            "total_size": _fmt_size(gs.total_size),
        }

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
