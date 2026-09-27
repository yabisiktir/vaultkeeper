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
- **Resolved — natural sort of `.` vs digits: VK is right.** NIT's `WinCompare`
  (`StrCmpLogicalW`) measured under Wine sorts `.` *after* digits, so ungrouped
  mods (`......001`) outrank "000.  Restorers"; VK's `win_compare` sorts `.`
  *before* digits. NIT's own help settles it for Windows: "Ungrouped Mods always
  appear at the top of your Mod list, which means they will have the lowest
  priority when the Installer Tool is dealing with file conflicts." So under
  Wine NIT gets its own priority wrong. Consequence for comparisons: in the
  "restorer" scenario (a restorer holding a user file, then an *ungrouped* mod
  with the same file installed) NIT-under-Wine installs the mod's copy, VK keeps
  the restorer's — VK matches NIT on Windows. (Before the S3 fix this was hidden:
  with CRC 0 the restorer never counted as installed.)
- **Stage-2 re-run after the sixth–ninth batches (2026-09-27):** basic, deps,
  update, restorer, archives. deps and basic identical in every mod state and
  game file; archives identical (A1 kept archive and N1 names now agree; only a
  1-byte fixture-size difference, each side generates its own archives);
  restorer differs only by the Wine sort above. update: NIT labels Alpha
  *Installed* while its own file data has Alpha's `shared.2da` *Overridden*;
  NIT's `SetModState` gives *Installed and Overridden* for those file states (as
  NIT shows in "basic"), so NIT's label is stale — its `UpdateFileStates` runs on
  a background thread (`ProcessAsThread`). VK shows *Installed and Overridden*.
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
| R3 ✅ | Rule-defined install wizards (38 projects) never used |
| R4 ✅ | Per-file prerequisites (`RequiredFiles`, 32 projects) ignored |
| R5 ✅ | `IncludeExtensions`, `ExcludeDirectLinks`, `ApplyExcludes`, `ExcludeRequiredProjects`, `ExternalFile` not parsed (26 projects) |
| R9 ✅ | **New, found while fixing R2:** the file-wide exclusions were parsed by nobody. `Contains` / `StartsWith` / `EndsWith` (20 + 9 + 4 description patterns: "outdated", "Mac ", " old", Project Q's "ARCHIVE - QV"…) and the `.txt` extension rule held nothing back in any project. Also a bare `IgnoreExcludes` opened a swallowed block, so Project Q Archive's `Downloads` list was lost. |

(R1c is stage 1's R1 — renamed here to avoid clashing with the restorer finding.)

**R3 fixed (seventh batch):** wherever a mod's wizard is read (install prompt,
installer build, Wizard Builder, Validate), a mod without a wizard file now falls
back to the rules' wizard, looked up as VB `GetWizardInfo` does (project title,
else mod folder or "<mod> Installer Wizard" title); a lone SelectOne is dropped.
`stage1/diff_rule_wizards.py`: all 38 live-file wizards match NIT on title,
ExtractArchives, texts, SelectOne, SelectMany (keys, labels, default ticks),
InstallerExcludes and RunWizard; one cosmetic difference — a default label NIT
builds with its CamelCase splitter ("Th1 Bonus Portraits" vs VK "Th1
Bonusportraits"). **Found on the way (also fixed):** wizard entries that point
inside an archive (`aribeth_4.7z\override_1.79.8191+`, used by many rule
wizards) could never match, because VK extracted archives into `x0000` folders;
archives now extract into a folder named after the archive, as NIT's
`ExtractedZips`, and the ignore list accepts folders. Verified with real 7-Zip.
**Fixed too (tenth batch):** NIT's download-time `UpdateWizard` — when Download
Project retires or deletes files a new download replaces, the wizard's entries
that name them are rewritten (same version stem or dated name), the mod's own
wizard silently, a rules wizard saved as the mod's own only after asking; the
CEP 2 wizard is left alone. `ProfileController.wizard_update_for_download`,
`tests/test_wizard_update_on_download.py`.

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
| A1 ✅ | Pasted archive not kept in the mod's `_Downloads` — fixed: Add Mods from Files moves it there (copies when "Use Move (rather than Copy) when adding files" is off), a clipboard paste copies it. Note: NIT's `BehaviourMoveAddedMods` *is* that move/copy preference; VK's `move_added_mods` is a separate VK default-group option that reused the name. |
| S3 ✅ | Mod state after uninstall/override differs (VK shows "Some and Match" for a mod whose file is another mod's copy) — fixed: the cause was missing CRCs. After building an installer VK scanned its files but never checksummed them (VB `UpdateProfileData` runs `CalculateChecksums` first), so every new file had CRC 0 and same-named files "matched". `ProfileData.update_file_states` now checksums pending mod files first. Re-ran stage 2 "basic" against NIT: every mod state matches at every step. NIT's earlier "Not Installed" for Alpha after its uninstall did not reproduce — NIT now gives "Some and Overridden", like VK: NIT runs `UpdateFileStates` on a background thread (`ProcessAsThread`), so that label is timing-dependent in NIT. The harness snapshot now includes enum properties (`FileState`). |
| N1 ✅ | Mod names from raw archive names not tidied (`angel_falls_prelude_v24`) — fixed: `core/mod_names.mod_name_from_file` ports `ModNameFromFile`'s word rules for raw names (underscores or no capitals) and leaves clean names alone. Checked with the harness `modname` query on 26 names: 23 identical to NIT; the 3 others are deliberate (NIT's "MIX of Things", "Tales of Arterra ( EE)", "CEP V2.x"). Applies to archives; a pasted *folder* keeps its name (its installer identifier carries it). |
| M2 ✅ | `nitconfig` folders always excluded — verified harmless and kept (VK-better): the only files there are identifiers. The mod's own identifier is written by the build anyway; a foreign `.nitins`/`.nitres` that NIT would copy into the installer would mark that other mod installed (or make this mod look like a restorer) whenever this one is installed. Pinned by `tests/test_installer_nitconfig_source.py`. |

## Stage 3a — first run, profiles, INI (details: `stage3a_first_run.md`)

| ID | Finding |
|---|---|
| F1 ✅ | First run never offered "Create Restorers for files installed by NWN?" (menu only) |
| F1b ✅ | Original restorers grouped per module file (~26) instead of NIT's per campaign / per bundled module, no edition suffix |
| P1 ✅ | Profiles not checked against the game folder when opened / switched (NIT: `CheckInstalledFiles` + anneal on every load) |
| P2 ✅ | `check_installed_files` left mods "installed" in files that vanished, and did not checksum added/changed files |
| F3 | NIT writes `NWMFiles`/`SOURCEOVERRIDE`/`PATCH` aliases into nwn.ini — deliberate not to (VK better; S4 closed) |
| F2 | Empty `userpatch.ini` at first run (NIT) vs first install (VK) — harmless |

## Stage 3b — settings (details: `stage3b_settings.md`)

| ID | Finding |
|---|---|
| B1 ✅ | BIK→WBM conversion default off (NIT on); a failed conversion dropped the movie |
| B2 ✅ | Select-the-played-mod default off (NIT on) |
| B3 ✅ | Minimum recorded play session 1 min (NIT 10) |
| B4 ✅ | Delete did not uninstall, delete the folder or anneal (NIT does; installed files were orphaned) |
| B5 ✅ | Importing a mod you have lost your group/properties, merged over the old folder, left the install stale |
| B6 ✅ | A download with no rule group went into "000.  Restorers" (first group) instead of "810.  Evaluating" |

## Stage 3c — backups and recovery (details: `stage3c_recovery.md`)

| ID | Finding |
|---|---|
| C1 ✅ | Validate Profile Data only pruned dependencies (NIT: Validate Installed Data + Validate Mods) |
| C2 ✅ | Validate Installed Data skipped the anneal and NIT's per-record repair (`ValidateInstalledFileData`) |
| C3 ✅ | Restore Data trusted the backup's picture of the game (NIT's restart re-checks it) |
| C4 | Rebuild Database keeps groups/properties in VK (NIT loses them) — VK better |

## Stage 3d — game saves (details: `stage3d_saves.md`)

| ID | Finding |
|---|---|
| G1 ✅ | Save-name → mod mapping was case-sensitive (NIT's is not): a case difference made VK ask the user |
| G2 ✅ | Reduce kept 100 saves, not remembered (NIT: 50, remembered) |
| G3 ✅ | No warning after play when there are more than 700 saves (NIT warns) |

## Stage 3e — play data and logs (details: `stage3e_play_data.md`)

| ID | Finding |
|---|---|
| E1 ✅ | Hak files the game could not load were parsed but never shown (NIT: "Module Load Failure") |
| E2 ✅ | Log markers matched case-sensitively (NIT: case-insensitive) |

## Stage 3f — installer tooling (details: `stage3f_installer_tooling.md`)

| ID | Finding |
|---|---|
| F1 ✅ | Add Files put files in the installer, not the mod folder: lost on the next rebuild, archives left packed |
| F2 ✅ | No way to add files to an installer (NIT's installer paste / `UpdateInstaller`) |
| F3 ✅ | The status bar's Overwrite toggle was read by nothing |
| F4 ✅ | Re-publishing added into the old archive (stale files kept); NIT asks and recycles it |
| F5 ✅ | Publish could not generate the Installation Guide |
| F6 ✅ | "Install after create" left a rebuilt, previously installed mod uninstalled |
| F7 ✅ | Convert Restorer left the payload only in the installer (latent loss on rebuild) |
| F8 ✅ | No offer to build the installer after saving a wizard |
| F9 ✅ | No wizard file-count threshold warning |

## Stage 3g — portraits and start screens (details: `stage3g_portraits_start_screens.md`)

| ID | Finding |
|---|---|
| P1–P3 ✅ | Portrait excludes / Create Installer never rebuilt the payload; excludes missed portraits inside archives |
| P4 ✅ | Override textures ending in "h" listed as portraits |
| P6 ✅ | Edit Portrait edited the installed copy, not the mod's source |
| T1–T2 ✅ | Auto-Start Screen Selection never rotated; Shift/Ctrl+right-click Play missing |
| T3 ✅ | Start-screen delete was a hard delete (NIT recycles) |
| T4 ✅ | Reselection after delete could pick an excluded image and flip the set |
| T5 ✅ | NIT's rename bug was replicated by default and stopped rotation |

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
- Stage 3h–3j: Workshop, documents, characters.
- `wizard_file_threshold` and `saves_threshold` are not in the Settings dialog.
- Stage 4 residual code review; Stage 5 fixes.
