# Phase 1 — Domain core

Goal: the single source-of-truth domain layer, ported faithfully from VB, fully
headless and tested. This is where the previous port failed, so every
correctness-critical value/behaviour is verified against the VB source and
covered by tests. Native store format; legacy NRBF import stays deferred.

## Resumption note (read this first if continuing a fresh session)

Vaultkeeper repo: `NWN Installer Tool/vaultkeeper` (own git). Dev env: `.venv` on
Python 3.13 (`./.venv/bin/python`, `./.venv/bin/pytest`, `./.venv/bin/ruff`).
Run tests: `./.venv/bin/python -m pytest -q`. Phase 0 is committed & complete.
VB ground truth: `../NWN Installer Tool/*.vb`. Reports in `../rehaul/`.
Work in committed increments; update the checklist below + memory as you go.

## Build order & status

- [x] **`core/win_sort.py`** — DONE (commit ccbf747). `win_compare` = StrCmpLogicalW
      (lower, lower), natural/numeric-aware. 3-way, total order. Tested.
- [x] **`core/file_key.py`** — DONE (commit ccbf747). `FileKeyInfo`: FullKey identity
      (`Group\ModName\Folder\Filename`), case-insensitive equality+hash, `comparer`
      by (qualifier, file_key), predicates, installed_key, from_full_key. Tested
      incl. dict-key case-insensitivity + winner selection.
- [x] **data records** — DONE (commits aa42108, 38f3494, ed805ad).
  - group_member.py (view over ModList) + change_data.py (ChangeData/InfoFiles/
    InfoMods with save/merge/restore) landed in ed805ad.
  - [x] `core/state.py` — State + Ratings IntEnums (data-contract values verified).
        Commit aa42108.
  - [x] `core/file_data.py` — FileData + InstalledFileData records (fields + pure
        derived props + clone). Commit aa42108. **Deferred** to ProfileData: the
        pfd-coupled transitions on InstalledFileData (Installer setter/resolver,
        reset_mod_files, installer_conflicts, remove_mod_file, remove_file, rename)
        — VB refs in file_data.py comments + InstalledFileData.vb.
  - [x] `core/mod_data.py` — ModData record + set_mod_state machine + Weapon/
        GroupStatus enums. Commit 38f3494. Deferred to ProfileData: rename/remove/
        remove_file/remove_all_files/create_installer/update_file_keys/
        rebuild_file_list/path+notes resolution.
- [x] **`core/mapper.py`** — DONE (commit fc3d0c9). Default v21 tables +
      GetMappedFolder ladder + predicates + EE tweaks, name-level. 26 tests.
      Deferred: settings persistence/editors/import/migrations (Phase 8),
      folder-name->abs-path resolution (needs Paths).
- [x] **`core/profile_data.py`** — DONE.
  - [x] In-memory engine (commit 2ce293c): container, accessors, graph ops,
        state pipeline + core/ci_dict.py. Conflict-winner resolution tested.
  - [x] Disk-scan slice (commit 03f175b): scan_mods/scan_mod_files/scan_installed +
        calculate_checksums + Mapper.nwn_folder_paths. End-to-end scan tested.
  - [x] Native save/load slice (commit 2b2458b): persistence/profile_store.py
        (to_dict/from_dict/save_profile/load_profile) + initialise_groups.

## PHASE 1 COMPLETE

7 commits (aa42108, 38f3494, ed805ad, fc3d0c9, 2ce293c, 03f175b, 2b2458b). The
headless domain core is done and tested: FileKeyInfo/win_sort, State/Ratings/
Weapon enums, FileData/InstalledFileData/ModData/GroupMemberData/ChangeData,
Mapper, and ProfileData (load/scan/rebuild/save + state pipeline + checksums).
219 tests, ruff clean, Python 3.13.

## Still deferred to their consuming phases (NOT Phase 1)

These VB methods are install-engine / UI operations and land where they're used:
- ModData.rename/remove/create_installer/update_file_keys/rebuild_file_list and
  GroupMemberData.rename/add_members -> Phase 2/3 (install engine / main window).
- FileKeyInfo.FullName / FileData.FullName absolute-path resolution beyond the
  scan/checksum helpers -> as needed with the Paths integration.
- Mapper settings persistence / editors / import / version migrations -> Phase 8.
- Legacy NRBF importer (read existing NIT Store) -> later, per hybrid strategy.

## NEXT: Phase 2 — install engine

HakPatchManager, ModInstallationManager (InstallFiles/UninstallFiles/Anneal with
the invariants: <5121B always-copy CRC guard, winner=last by comparer, nwnpatch.ini
rebuild each op, double UpdateProfileData + change-info save/merge/restore), a
FileOperations-equivalent worker, CalculateCRCs. Golden tests vs a sample profile.

## Key VB constants captured (added to core/constants.py)

- ModRoot folder = `"nwn"`; ModNit = `"nitconfig"`; ExtInstaller = `".nitins"`;
  ExtRestorer = `".nitres"`; ModFile = `".mod"` (+ `.nwm`); Installer dir =
  `".Mod Installer"`; InstalledFiles label = `"Installed Files"`;
  GroupInstalled = `"......000"`.

## Decisions

- FileKeyInfo equality/hash are **case-insensitive** on FullKey (see above).
- `win_compare` reimplements StrCmpLogicalW numeric-aware natural order; documented
  edge case: leading-zero tie-break approximated (rare in real filenames).
- `FullName`/`CrashReportFullName` (which need Paths/Mapper runtime) are deferred
  to resolver helpers once Mapper/Paths land, not baked into the value object.
