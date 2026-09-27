# Logic audit — findings index (stages 1–2)

Ranked by user impact. Details and evidence in `stage1_findings.md` /
`stage2_findings.md`. Triage: BUG = Vaultkeeper worse than NIT.

## Data safety / silent wrong content

| ID | Finding | Area |
|---|---|---|
| R1 ✅ | Create Restorer doesn't back up unowned installed files; a user's own override file is lost after a mod overwrites it and is uninstalled (NIT restores it) | restorers |
| U1 ✅ | Conflict winner follows batch order, not mod priority (install A+B together → VK keeps A's file, NIT B's) | install |
| S1 ✅ | EE patch-hak list written to `<game install>/nwnpatch.ini` instead of `<user>/userpatch.ini`; VK also writes into the install folder | install |
| U3 ✅ | Files deleted from a mod's source survive an installer rebuild and stay in the game | installer build |
| S2 ✅ | NIT-managed "(Auto)" restorers (database, INI, journals, NIT config) missing | restorers |
| M3 ✅ | **EE root folder maps to the install folder.** NIT's live table: on EE `nwn` = the *user* folder (`NwnFolders=nwn=<user>`); VK maps it to `game_root`. So VK installs mods' `.ini`/`.tml`/`.key`/`.dll`/`dialog.tlk` into the game installation folder, and never scans the user folder's own `nwn.ini`/`settings.tml` — which is why the INI auto-restorer (S2) finds nothing on EE. Fixing it moves where root files install, so existing installs need a migration. | mapping |
| M1 ✅ | Mods shipping `ovr/`, `mus/`, `txpk/`, EE `mod/` folders are routed by extension instead of into those folders | mapping |

✅ = fixed 2026-09-27 (stage 5, first batch). Each has regression tests that fail
on the old code (`tests/test_install_conflict_priority.py`,
`test_patch_ini_location.py`, `test_installer_rebuild.py`,
`test_create_restorer_unowned.py`) and was re-verified against NIT by rerunning
the stage-2 scenarios (deps, update, restorer: final game state identical).

Notes from the fixes:
- **M1 fixed** (fifth batch): `Mapper._apply_ee` adds VB DefineEeFolders' rules
  (ovr, mod, mus, txpk); without EE, "ovr" rules use override. Stage-1 corpus
  rerun vs NIT: 3,234 → 386 mismatches per mode, all M2 (nitconfig). Note: as in
  NIT, a folder literally named mod/mus/ovr/txpk (even a mod's own folder) is a
  folder rule.
- **M3 fixed** (fourth batch): on EE `nwn` resolves to the user folder and
  root files are keyed by its name. Profiles made earlier are migrated when
  opened: a root file recorded as installed by one of the profile's mods, still
  in the install folder and identical to the mod's copy, moves to the user
  folder (never over an existing file); nothing else in the install folder is
  touched. Dry run on the owner's real data: only `desktop.ini` (Adreannadreas
  Portrait Collections) moves. Remaining fresh-start differences vs NIT: NIT's
  first run asks "Create Restorers for files installed by NWN?" (→ "2. NWN INI
  Files Restorer") and creates an empty `userpatch.ini`; VK does neither at
  first run (stage 3, first-run flow).
- **S2 fixed** (third batch): `ProfileController.run_auto_restorers` ports
  `RunAutoRestorers` (database, INI, journal, NIT config; the character one
  already existed), run at start-up and after a game/toolset session.
  On EE the INI restorer needed M3 (fixed in the next batch). Also found: `rescan_installed_state` keeps the record of a game
  file that has vanished from disk (the restorers check the disk instead).
- **U2 fixed too** (second batch): `installer_restore` defaults to True as in
  NIT, and settings version 2 turns it on once in existing settings files (every
  field is saved, so the old wrong default was in all of them). The update
  scenario now matches NIT at the rebuild step.
- **Open question — natural sort of `.` vs digits.** NIT's `WinCompare`
  (`StrCmpLogicalW`) measured under Wine sorts `.` *after* digits, so ungrouped
  mods (`......001`) outrank "000.  Restorers" and even "100.  Community Packs";
  VK's `win_compare` sorts `.` *before* digits. Group priority therefore differs
  whenever an ungrouped mod conflicts with a grouped one. Needs a check on real
  Windows before deciding which is right.
- NIT creates an empty `userpatch.ini` at first run; VK creates it at the first
  install (the game treats a missing file as empty).
- **Incident:** the first S1 fix wrote `userpatch.ini` into the developer's real
  `~/Documents/Neverwinter Nights` during the test suite (an EE profile opened
  without an explicit user folder fell back to the platform default). Content was
  an empty patch list, as before; line endings changed CRLF → LF. Fixed by using
  only the explicit EE user folder (`InstallContext.ee_user_files_dir`) and by
  isolating `nwnfile.locations._home` in `tests/conftest.py`.

## Downloads (Vault rules)

| ID | Finding |
|---|---|
| R2 ✅ | `If EE/NWN Downloads` conditionals dropped: Community Patch ×2 lose mod folder + EE archive; 12 wrong/empty download whitelists |
| R1c ✅ | Per-project `ExcludeFiles From` blocks ignored (12 projects offer files NIT holds back) |
| R3 | Rule-defined install wizards (38 projects) never used |
| R4 ✅ | Per-file prerequisites (`RequiredFiles`, 32 projects) ignored |
| R5 ✅ | `IncludeExtensions`, `ExcludeDirectLinks`, `ApplyExcludes`, `ExcludeRequiredProjects`, `ExternalFile` not parsed (26 projects) |
| R9 ✅ | **New, found while fixing R2:** the file-wide exclusions were parsed by nobody. `Contains` / `StartsWith` / `EndsWith` (20 + 9 + 4 description patterns: "outdated", "Mac ", " old", Project Q's "ARCHIVE - QV"…) and the `.txt` extension rule held nothing back in any project. Also a bare `IgnoreExcludes` opened a swallowed block, so Project Q Archive's `Downloads` list was lost. |

(R1c is stage 1's R1 — renamed here to avoid clashing with the restorer finding.)

**Fixed (sixth batch):** `DownloadRules` now reads every per-project field NIT
reads and the file-wide exclusion tables. Game-dependent lines are kept aside
and settled per profile by `ProjectRule.for_game` / `DownloadRules.rule_for_game`
(EE counts as 1.69; `If ERF` files held back, NIT's default). Applied in
`ProfileController._apply_project_rules` in NIT's order (`IsExcluded` unless
`IgnoreExcludes`, then the `Downloads` whitelist); external files join the list;
prerequisites are added, removed (`ExcludeRequiredProjects`,
`ExcludeDirectLinks`) and given their `RequiredFiles From` list, which overrides
the prerequisite's own rules as in NIT. Re-diffed against NIT's parse of the same
2,602-line published file (`stage1/diff_rules_full.py`): all 227 projects agree on
every field; the three remaining lines are dump-format artefacts (two titles
contain `|` / `:`) and R7. Regression tests: `tests/test_download_rules_nit_parity.py`
(all 13 fail on the old code). Not yet done: replaying recorded Vault responses to
both apps' download dialogs (stage 1c follow-up). NIT's non-EE version detection
(1.68 vs 1.69) is not ported; a classic profile is treated as 1.69.

## Behaviour / defaults / display

| ID | Finding |
|---|---|
| U2 ✅ | Rebuilt installer of an installed mod isn't reinstalled (VK `installer_restore` default False; NIT True) |
| A1 | Pasted archive not kept in the mod's `_Downloads` |
| S3 | Mod state after uninstall/override differs (VK shows "Some and Match" for a mod whose file is another mod's copy) |
| N1 | Mod names from raw archive names not tidied (`angel_falls_prelude_v24`) — port the tidy-up without NIT's `( EE)` bug |
| M2 | `nitconfig` folders always excluded (deliberate; effect on re-created installers unverified) |

## Vaultkeeper better than NIT

| ID | Finding |
|---|---|
| S6 | NIT's LazWorks `FileOperations` queue race leaves files behind on install/uninstall (hit on every unpatched run under Wine) |
| R6/R7 | NIT keeps "End Exclude" as a file name; mis-decodes `’` in a URL |
| N2 | NIT mangles clean names ("Tales of Arterra ( EE)") |

## Matches (verified, not just "ported")

File mapping on 39k real+synthetic paths (apart from M1/M2); install, uninstall,
conflict annealing for sequential installs; dependency install/uninstall; outside
edits + rescan; archive extraction incl. nested archives and single-top-folder
layouts.

## Still open

- Stage 1c follow-up: replay recorded Vault responses to both apps' download
  selection (which files each offers) for the R-findings' projects.
- Stage 3 (other features), incl. profile create/switch, INI aliases (S4),
  Game Saves Manager, backups, play data, portraits/start screens, Workshop.
- Stage 4 residual code review; Stage 5 fixes.
