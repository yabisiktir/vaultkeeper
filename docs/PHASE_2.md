# Phase 2 — Install engine

Goal: faithful, headless port of the install/uninstall/anneal engine — the
correctness heart of NIT — with its load-bearing invariants intact and covered by
golden tests against a sample profile.

## Resumption note

Repo `vaultkeeper` (own git). Dev: `./.venv/bin/{python,pytest,ruff}` (py3.13).
Phase 1 complete (domain core + ProfileData). VB truth: `../NWN Installer Tool/*.vb`
(ModInstallationManager.vb fully read; HakPatchManager.vb pending). Commit each
increment; update this checklist + memory.

## Invariants that MUST be preserved (from ModInstallationManager.vb)

- **Small-file guard**: a file whose byte_size < 5121 is always copied even if the
  CRC matches (`NoCrcCheckRequired = 1024*5+1`). Guards CRC collisions.
- **Winner selection**: among installed conflicting mods, the winner is the LAST
  by `FileKeyInfo.comparer` (install: `conflicts.index(fk) < count-1` means
  overridden; uninstall: candidates sorted then reversed, take [0]).
- **nwnpatch.ini** is rebuilt after every install and uninstall.
- **Double UpdateProfileData**: UpdateProfileData is called, then
  `Changes.MergeSavedInfo()`, then UpdateProfileData again — required to avoid
  errors in the install→uninstall→install sequence.
- **Change-info choreography**: SaveInfo/ResetChanges around the copy; SaveInfo/
  ResetChanges around the Anneal; RestoreSavedInfo after. Auto-anneal runs after
  installs over the selected mods.
- EE: on uninstall, companion `.sqlite3` files of database-extension files are
  also deleted. Patch-ini files only get a state flip, not a physical delete.

## Build order & status

- [ ] `core/file_ops.py` — headless batch copy/delete worker (LazWorks
      FileOperations analogue): per-item results, CRC stamping. NEXT.
- [ ] `core/hak_patch.py` — HakPatchManager.create_nwn_patch_ini_file (rebuild the
      game patch ini from installed haks). Port from HakPatchManager.vb.
- [ ] `core/install_manager.py` — ModInstallationManager: install_files /
      uninstall_files / anneal. UI concerns (FvMods selection, status text,
      SetCountInfo, save) parameterized/injected so it runs headless.
- [ ] ProfileData.add_installed_file(ifk, path) helper (AddInstalledFile).
- [ ] Golden tests: build a sample profile on disk, install/uninstall/anneal,
      assert file states, installer ownership, and physical file presence.

## Notes

- CalculateCRCs is already covered by ProfileData.calculate_checksums (Phase 1).
- FileData/InstalledFileData FullName resolution uses the Phase-1 path helpers
  (mod_file_path / installed_file_path) with profile_mods_dir + game_folders.
