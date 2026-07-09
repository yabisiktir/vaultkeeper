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
    ) -> ProfileController:
        """Load a profile from ``store_path`` (or scan from disk if absent), wire it up."""
        mapper = Mapper(
            is_ee=is_ee,
            overrides=map_overrides,
            exclude_overrides=map_exclude_overrides,
        )
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
        return cls(pd, ctx, store_path=store_path, settings_path=settings_path)

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

    def build_installer_payload(self, mod_name: str) -> dict:
        """Populate a mod's ``.Mod Installer`` payload from its raw/downloaded files.

        The faithful heart of VB Create Installer (``CreateInstaller``): scan the mod
        folder, extract any downloaded archives (via the injected extractor seam),
        analyse every file through the Mapper into the ``CopyList``, then copy each
        winning file into ``.Mod Installer/<folder>/<filename>``. Afterwards the mod
        is (re)marked an installer, its file list rescanned and states recomputed,
        and the profile persisted — mirroring :meth:`add_files_to_mod`.

        Bounded (see ``game/installer_build``): BIK→WBM conversion, the
        ``nwnpatch.ini`` patch-hak reassignment and the wizard select-one/many modal
        flow are deferred. Returns ``{"ok", "copied", "excluded", "archives",
        "message"}``.
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
                "message": f"Unknown mod: {mod_name}",
            }

        mod_folder = self.ctx.profile_mods_dir / mod_name
        installer = mod_folder / C.MOD_INSTALLER_DIR
        installer.mkdir(parents=True, exist_ok=True)

        # Extract archives into a temp area that survives until the copy is done.
        with tempfile.TemporaryDirectory(prefix="vk-installer-") as extract_dir:
            plan = build_copy_plan(
                mod_name,
                mod_folder,
                mapper=self.ctx.mapper,
                extractor=self._archive_backend(),
                extract_root=Path(extract_dir),
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

        # Mark as an installer; _create_identifier rescans the payload, recomputes
        # file/mod states and persists (like add_files_to_mod's tail).
        self._create_identifier(mod_name, C.EXT_INSTALLER)

        return {
            "ok": True,
            "copied": copied,
            "excluded": len(plan.excluded),
            "archives": plan.archives_extracted,
            "message": (
                f"Built installer for {mod_name}: {copied} file(s) copied"
                + (
                    f", {plan.archives_extracted} archive(s) extracted"
                    if plan.archives_extracted
                    else ""
                )
                + (f", {len(plan.excluded)} excluded" if plan.excluded else "")
                + "."
            ),
        }

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
                    "group": md.group,
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
            for entry in scan_mod_docs(
                name, mod_folder, extractor=extractor, remove_version=remove_version
            ):
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

        Only loose ``_Downloads`` files can be copied: a source that no longer exists
        (e.g. an archive-extracted doc whose temp copy is gone) is counted as an
        error. Copying docs back out of archives is deferred.
        """
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
        for sel in selections:
            source = Path(sel["source"])
            doc_name = sel["doc_name"]
            if not doc_name or not source.is_file():
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

    def validate_wizard(self, mod_name: str, *, save: bool = False) -> dict:
        """Prune a wizard's dead entries against the mod's real files (VB ``Validate``).

        Loads the mod's wizard, scans its actual files, and removes SelectOne /
        SelectMany / InstallerExcludes entries that no longer point at a real file.
        By default this is in-memory only (VB ``Validate``); pass ``save=True`` to
        persist the cleaned wizard. If a duplicate file/archive name is found the scan
        is suppressed (VB ``SuppressWizardCreation``) and nothing is pruned. Returns
        ``{ok, has_wizard, removed, saved, suppressed, duplicate, message}``.

        Archives are listed but not extracted, so entries referencing files *inside*
        an archive are treated as missing — see the module note (deferred).
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
