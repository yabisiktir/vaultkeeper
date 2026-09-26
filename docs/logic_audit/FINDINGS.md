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
| S2 | NIT-managed "(Auto)" restorers (database, INI, journals, NIT config) missing | restorers |
| M1 | Mods shipping `ovr/`, `mus/`, `txpk/`, EE `mod/` folders are routed by extension instead of into those folders | mapping |

✅ = fixed 2026-09-27 (stage 5, first batch). Each has regression tests that fail
on the old code (`tests/test_install_conflict_priority.py`,
`test_patch_ini_location.py`, `test_installer_rebuild.py`,
`test_create_restorer_unowned.py`) and was re-verified against NIT by rerunning
the stage-2 scenarios (deps, update, restorer: final game state identical).

Notes from the fixes:
- **U2 is now more visible.** Rebuilding an installed mod uninstalls it first
  (NIT's sequence); with VK's `installer_restore` default False it then stays
  uninstalled until installed again. NIT's default is True. Fix next.
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
| R2 | `If EE/NWN Downloads` conditionals dropped: Community Patch ×2 lose mod folder + EE archive; 12 wrong/empty download whitelists |
| R1c | Per-project `ExcludeFiles From` blocks ignored (12 projects offer files NIT holds back) |
| R3 | Rule-defined install wizards (38 projects) never used |
| R4 | Per-file prerequisites (`RequiredFiles`, 32 projects) ignored |
| R5 | `IncludeExtensions`, `ExcludeDirectLinks`, `ApplyExcludes`, `ExcludeRequiredProjects`, `ExternalFile` not parsed (26 projects) |

(R1c is stage 1's R1 — renamed here to avoid clashing with the restorer finding.)

## Behaviour / defaults / display

| ID | Finding |
|---|---|
| U2 | Rebuilt installer of an installed mod isn't reinstalled (VK `installer_restore` default False; NIT True) |
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
