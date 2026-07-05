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
- [~] **data records** — IN PROGRESS.
  - [x] `core/state.py` — State + Ratings IntEnums (data-contract values verified).
        Commit aa42108.
  - [x] `core/file_data.py` — FileData + InstalledFileData records (fields + pure
        derived props + clone). Commit aa42108. **Deferred** to ProfileData: the
        pfd-coupled transitions on InstalledFileData (Installer setter/resolver,
        reset_mod_files, installer_conflicts, remove_mod_file, remove_file, rename)
        — VB refs in file_data.py comments + InstalledFileData.vb.
  - [ ] `core/mod_data.py` — ModData (ModData.vb, 1053 lines): mod OR group row,
        SetModState machine, folder layout, user properties (rating/levels/weapon/
        hench/weblink/completed/workshopid/dates), Rename (renames folder + rewrites
        file keys), type file (.nitins/.nitres). LARGE.
  - [ ] `core/group_member.py` — GroupMemberData (GroupMemberData.vb, 246).
  - [ ] `core/change_data.py` — ChangeData (ChangeData.vb, 813): Installed/File/Mods
        sub-trackers; SaveInfo/RestoreSavedInfo/MergeSavedInfo (load-bearing for the
        install→anneal choreography).
- [ ] **`core/mapper.py`** — `Mapper.GetMappedFolder` ladder + tables/defaults.
      VB: `Mapper.vb` (3,124 lines; MapVersion 21). The engine the old port faked.
- [ ] **`core/profile_data.py`** — unified `ProfileData`: load/scan/rebuild/save +
      state pipeline + checksums, headless. VB: `ProfileData*.vb`.

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
