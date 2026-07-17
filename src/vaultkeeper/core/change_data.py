"""ChangeData — the change accumulator driving checksum/state updates and reporting.

Ported from ``ChangeData.vb``. It tracks, since the last reset, which mod files
and installed files were added/removed/changed/renamed and which mods were
added/removed/affected. The install engine uses the ``save_info`` /
``restore_saved_info`` / ``merge_saved_info`` choreography to preserve change
context across nested install→anneal sequences, so that ordering is reproduced
exactly.

Two comparison notes:

* File lists compare by ``FileKeyInfo`` identity (case-insensitive full_key), so
  Python ``in`` / list ops work directly.
* Mod-name membership is treated **case-insensitively** here (VB mixed an ordinal
  ``List.Contains`` guard with a case-insensitive ``=`` find; mod names are unique
  case-insensitive keys, so we standardise on case-insensitive to stay correct on
  case-sensitive filesystems).

Presentation-only members (``StatusLine``/``GetReport``/``Report``) are deferred
to the UI layer; the accumulator mechanics live here.
"""

from __future__ import annotations

from vaultkeeper.core.file_key import FileKeyInfo


def _ci_index(names: list[str], name: str) -> int:
    lowered = name.lower()
    for i, existing in enumerate(names):
        if existing.lower() == lowered:
            return i
    return -1


def _ci_contains(names: list[str], name: str) -> bool:
    return _ci_index(names, name) != -1


class InfoFiles:
    """Change tracking for a set of files (mod files or installed files)."""

    def __init__(self) -> None:
        self.added_list: list[FileKeyInfo] = []
        self.removed_list: list[FileKeyInfo] = []
        self.changed_list: list[FileKeyInfo] = []
        self.renamed_list: list[FileKeyInfo] = []
        self.illegal_folders: list[FileKeyInfo] = []
        self.illegal_files: list[FileKeyInfo] = []
        #: Added + Changed — the files whose checksums must be recalculated.
        self.update_list: list[FileKeyInfo] = []

    # -- derived ----------------------------------------------------------- #
    @property
    def illegal_items(self) -> bool:
        return (len(self.illegal_folders) + len(self.illegal_files)) > 0

    @property
    def update_states(self) -> bool:
        return (len(self.update_list) + len(self.removed_list) + len(self.renamed_list)) > 0

    @property
    def changes_detected(self) -> bool:
        return (len(self.added_list) + len(self.removed_list) + len(self.changed_list)) > 0

    @property
    def adds(self) -> int:
        return len(self.added_list)

    @property
    def removes(self) -> int:
        return len(self.removed_list)

    @property
    def changes(self) -> int:
        return len(self.changed_list)

    @property
    def renames(self) -> int:
        return len(self.renamed_list)

    # -- mutators ---------------------------------------------------------- #
    def added(self, key: FileKeyInfo) -> None:
        if key not in self.added_list:
            self.added_list.append(key)
            self.update_list.append(key)
            self.delete_removed(key)

    def removed(self, key: FileKeyInfo) -> None:
        self.removed_list.append(key)

    def changed(self, key: FileKeyInfo) -> None:
        if key not in self.changed_list:
            self.changed_list.append(key)
            self.update_list.append(key)
            self.delete_removed(key)

    def delete_removed(self, fk: FileKeyInfo) -> None:
        if fk in self.removed_list:
            self.removed_list.remove(fk)

    def renamed(self, key: FileKeyInfo) -> None:
        if key not in self.renamed_list:
            self.renamed_list.append(key)

    def clone(self) -> InfoFiles:
        c = InfoFiles()
        c.added_list.extend(self.added_list)
        c.removed_list.extend(self.removed_list)
        c.changed_list.extend(self.changed_list)
        c.renamed_list.extend(self.renamed_list)
        c.illegal_folders.extend(self.illegal_folders)
        c.illegal_files.extend(self.illegal_files)
        c.update_list.extend(self.update_list)
        return c


class InfoMods:
    """Change tracking for mods (added/removed/affected). Case-insensitive names."""

    def __init__(self) -> None:
        self.added_list: list[str] = []
        self.removed_list: list[str] = []
        self.affected_list: list[str] = []

    @property
    def adds(self) -> int:
        return len(self.added_list)

    @property
    def removes(self) -> int:
        return len(self.removed_list)

    @property
    def affecteds(self) -> int:
        return len(self.affected_list)

    @property
    def update_states(self) -> bool:
        return (len(self.added_list) + len(self.removed_list)) > 0

    @property
    def changes_detected(self) -> bool:
        return (len(self.added_list) + len(self.removed_list) + len(self.affected_list)) > 0

    def added(self, modname: str) -> None:
        if not _ci_contains(self.added_list, modname):
            self.added_list.append(modname)
            self.delete_item(self.removed_list, modname)

    def removed(self, modname: str) -> None:
        if not _ci_contains(self.removed_list, modname):
            self.removed_list.append(modname)

    def affected(self, modname: str) -> None:
        if not _ci_contains(self.affected_list, modname):
            self.affected_list.append(modname)

    @staticmethod
    def delete_item(names: list[str], modname: str) -> None:
        idx = _ci_index(names, modname)
        if idx != -1:
            names.pop(idx)

    @staticmethod
    def name_exists(names: list[str], modname: str) -> bool:
        return _ci_contains(names, modname)

    def clone(self) -> InfoMods:
        c = InfoMods()
        c.added_list.extend(self.added_list)
        c.removed_list.extend(self.removed_list)
        c.affected_list.extend(self.affected_list)
        return c


class ChangeData:
    """Accumulates file/installed/mod changes; supports save/merge/restore."""

    def __init__(self) -> None:
        self.installed = InfoFiles()
        self.file = InfoFiles()
        self.mods = InfoMods()
        self.orphaned_mod_notes: list[str] = []

        # Snapshot storage for save_info / merge_saved_info.
        self._saved_file_added: list[FileKeyInfo] = []
        self._saved_file_removed: list[FileKeyInfo] = []
        self._saved_file_changed: list[FileKeyInfo] = []
        self._saved_file_renamed: list[FileKeyInfo] = []
        self._saved_installed_added: list[FileKeyInfo] = []
        self._saved_installed_removed: list[FileKeyInfo] = []
        self._saved_installed_changed: list[FileKeyInfo] = []
        self._saved_installed_renamed: list[FileKeyInfo] = []
        self._saved_mods_added: list[str] = []
        self._saved_mods_removed: list[str] = []
        self._saved_mods_affected: list[str] = []
        self._saved_orphaned_notes: list[str] = []

    # -- derived ----------------------------------------------------------- #
    @property
    def update_checksums(self) -> bool:
        return len(self.installed.update_list) > 0 or len(self.file.update_list) > 0

    @property
    def update_states(self) -> bool:
        return self.installed.update_states or self.file.update_states or self.mods.update_states

    @property
    def illegal_items(self) -> bool:
        return self.installed.illegal_items or self.file.illegal_items

    @property
    def detected(self) -> bool:
        return (
            self.mods.changes_detected
            or self.file.changes_detected
            or self.installed.changes_detected
        )

    # -- status line ------------------------------------------------------- #
    def _status_line_none(self, text: str) -> str:
        """``text`` with the orphaned-note count appended (VB StatusLineNone)."""
        if not self.orphaned_mod_notes:
            return text
        return f"{text}Orphaned Notes: {len(self.orphaned_mod_notes):,}. "

    def status_line(self) -> str:
        """One-line summary of accumulated changes for the status bar.

        Faithful to VB ``ChangeData.StatusLine`` with ``InstalledInfo | ModInfo``
        (the main status line): "Installed file and Mod changes: None. " when
        nothing is pending, else a breakdown of installed-file / mod / mod-file
        adds, changes and removes (with any illegal folder/file and orphaned-note
        counts).
        """
        if not self.detected:
            return self._status_line_none("Installed file and Mod changes: None. ")

        parts: list[str] = []
        inst = self.installed
        if inst.changes_detected:
            parts.append("Installed Files ")
            if inst.adds > 0:
                parts.append(f"Added: {inst.adds:,}. ")
            if inst.changes > 0:
                parts.append(f"Changes: {inst.changes:,}. ")
            if inst.removes > 0:
                parts.append(f"Removed: {inst.removes:,}. ")
            if inst.illegal_items:
                parts.append("Illegal ")
                if inst.illegal_folders:
                    parts.append(f"Folders: {len(inst.illegal_folders):,}. ")
                if inst.illegal_files:
                    parts.append(f"Files: {len(inst.illegal_files):,}. ")

        mods, file = self.mods, self.file
        if mods.changes_detected or file.changes_detected:
            # Affected count excludes mods also added or removed (VB filter).
            affecteds = sum(
                1
                for name in mods.affected_list
                if not _ci_contains(mods.added_list, name)
                and not _ci_contains(mods.removed_list, name)
            )
            parts.append("Mods " if (mods.changes_detected or affecteds > 0) else "Mod ")
            if mods.adds > 0:
                parts.append(f"Added: {mods.adds:,}. ")
            if mods.removes > 0:
                parts.append(f"Removed: {mods.removes:,}. ")
            if mods.affecteds > 0:
                parts.append(f"Affected: {affecteds:,}. ")
            if file.changes_detected:
                parts.append("Files ")
            if file.adds > 0:
                parts.append(f"Added: {file.adds:,}. ")
            if file.changes > 0:
                parts.append(f"Changes: {file.changes:,}. ")
            if file.removes > 0:
                parts.append(f"Removed: {file.removes:,}. ")
            if file.illegal_items:
                parts.append("Illegal ")
                if file.illegal_folders:
                    parts.append(f"Folders: {len(file.illegal_folders):,}. ")
                if file.illegal_files:
                    parts.append(f"Files: {len(file.illegal_files):,}. ")

        if self.orphaned_mod_notes:
            parts.append(f"Orphaned Notes: {len(self.orphaned_mod_notes):,}.")
        return "".join(parts)

    # -- lifecycle --------------------------------------------------------- #
    def reset_changes(self) -> None:
        self.installed = InfoFiles()
        self.file = InfoFiles()
        self.mods = InfoMods()
        self.orphaned_mod_notes.clear()

    def clone(self) -> ChangeData:
        c = ChangeData()
        c.installed = self.installed.clone()
        c.file = self.file.clone()
        c.mods = self.mods.clone()
        c.orphaned_mod_notes.extend(self.orphaned_mod_notes)
        return c

    # -- save / merge / restore (install→anneal choreography) -------------- #
    def save_info(self) -> None:
        """Snapshot current change lists for a later merge/restore."""
        self._saved_file_added = list(self.file.added_list)
        self._saved_file_removed = list(self.file.removed_list)
        self._saved_file_changed = list(self.file.changed_list)
        self._saved_file_renamed = list(self.file.renamed_list)
        self._saved_installed_added = list(self.installed.added_list)
        self._saved_installed_removed = list(self.installed.removed_list)
        self._saved_installed_changed = list(self.installed.changed_list)
        self._saved_installed_renamed = list(self.installed.renamed_list)
        self._saved_mods_added = list(self.mods.added_list)
        self._saved_mods_removed = list(self.mods.removed_list)
        self._saved_mods_affected = list(self.mods.affected_list)
        self._saved_orphaned_notes = list(self.orphaned_mod_notes)

    def merge_saved_info(self) -> None:
        """Merge the saved snapshot back into the current lists; clear update lists."""
        for fk in self._saved_file_added:
            self.file.added(fk)
        for fk in self._saved_file_removed:
            self.file.removed(fk)
        for fk in self._saved_file_changed:
            self.file.changed(fk)
        for fk in self._saved_file_renamed:
            self.file.renamed(fk)

        for fk in self._saved_installed_added:
            self.installed.added(fk)
        for fk in self._saved_installed_removed:
            self.installed.removed(fk)
        for fk in self._saved_installed_changed:
            self.installed.changed(fk)
        for fk in self._saved_installed_renamed:
            self.installed.renamed(fk)

        for name in self._saved_mods_added:
            self.mods.added(name)
        for name in self._saved_mods_removed:
            self.mods.removed(name)
        for name in self._saved_mods_affected:
            self.mods.affected(name)

        # De-duplicated union of orphaned notes.
        orphans = list(self._saved_orphaned_notes)
        orphans.extend(self.orphaned_mod_notes)
        self.orphaned_mod_notes.clear()
        seen: set[str] = set()
        for note in orphans:
            if note not in seen:
                seen.add(note)
                self.orphaned_mod_notes.append(note)

        self.file.update_list.clear()
        self.installed.update_list.clear()

    def restore_saved_info(self) -> None:
        """Reset current change lists to the saved snapshot (clears then merges)."""
        self.file.added_list.clear()
        self.file.removed_list.clear()
        self.file.changed_list.clear()
        self.file.renamed_list.clear()
        self.installed.added_list.clear()
        self.installed.removed_list.clear()
        self.installed.changed_list.clear()
        self.installed.renamed_list.clear()
        self.mods.added_list.clear()
        self.mods.removed_list.clear()
        self.mods.affected_list.clear()
        self.orphaned_mod_notes.clear()
        self.merge_saved_info()
