# Stage 4 — residual code review

Stages 1–3 ran NIT's own code (or compared it line by line) feature by feature.
Stage 4 covers what they could not: every member of the original that no stage
executed. Exit criterion (README): every residual row has a verdict backed by a
VB-vs-Python branch comparison, not a note.

## Method

`stage4/triage.py` puts each of the ledger's 3,284 members
(`../parity_audit/ledger_members.csv`) in one bucket:

| Bucket | Rows | Meaning |
|---|---|---|
| covered | 1,074 | its file was executed or compared line by line in a stage (`STAGE_FILES`) |
| no-logic | 1,134 | a *form* member whose body touches nothing a user keeps: no profile data, files, settings writes, mapper, processes or network |
| trivial | 162 | a data/logic-class member of three lines or fewer |
| n/a | 188 | ledger N/A (enums, plain properties, designer members) |
| **review** | **726** | everything else, reviewed by hand, core files first |

Members of data and logic classes are never "no-logic": a pure computation such
as `ModData.SetModState` changes nothing on disk yet decides what every mod shows.
The body extractor stops at the next member, so an auto-property does not swallow
the code after it (checked by sampling the largest bodies of each bucket).

Verdicts go in `stage4/verdicts.csv` (`same`, `fixed`, `deliberate`, `NIT
artefact`, `n/a`); `triage.py` then lists what is left in `stage4/residual.csv`.

## Batches

| # | Files | Rows | State |
|---|---|---|---|
| 1 | ModData.vb | 31 | ✅ |
| 2 | ProfileData.vb, ProfileData.Properties.vb, GroupMemberData.vb | 107 | ✅ |
| 3 | Paths.vb, ProfileInfo.vb, ProfileInfoManager.vb, NwnFolderInfo.vb | 111 | ✅ |
| 4 | HakPatchManager.vb, ErfFileReader.vb, InstallationAnalyser.vb, DependencyManager.vb | 41 | |
| 5 | NIT.Menu.vb, NIT.Common.vb, NIT.Workers.vb, NIT.ModView.vb, NIT.* views | ~160 | |
| 6 | Defs.vb, Settings.* | ~70 | |
| 7 | the rest (viewers, GameManager, ModExplorer, …); NetworkManager.vb as one verdict (not ported) | ~200 | |

## Batch 1 — ModData.vb

31 rows: 26 same, 5 fixed.

| Member | Finding | Verdict |
|---|---|---|
| `ValidateInstallerType` | NIT runs it for every mod with an installer on each profile load: duplicate file entries dropped; the identifier made to match what the mod is (`.nitins` with source files, `.nitres` without), renaming the installed copy too; a missing one created. VK never did: a restorer given source files (Add Files) stayed a restorer and Create Installer refused to build it. Ported as `validate_installer_types` (profile load and Validate Mods). Real-data dry run (read only): 11 mods checked, one gains its missing `.nitins`, nothing renamed. | MISSING → fixed |
| `CreateTypeFile` | `_create_identifier` wrote the new identifier and left the opposite one, so a mod could carry both (`update_installer` on a restorer). It now removes the other. | BUG → fixed |
| `Remove` | Deleting a mod recycles its notes in NIT; VK left them until Validate Mods. | fixed |
| `Rename` | Notes follow the mod (3i N1). | fixed earlier |
| `SetModState` | Same branch for branch (including NIT comparing the override count with the whole profile's file count); the `nwnpatch.ini` name test now ignores case, as `Option Compare Text` does. | fixed (minor) |

Regression tests: `tests/test_installer_type_parity.py`,
`tests/test_notes_parity.py::test_deleting_a_mod_recycles_its_notes`.

## Batch 2 — ProfileData, ProfileData.Properties, GroupMemberData

106 verdicts (two `RepairChecksums` overloads share one): 78 same, 15 fixed,
8 n/a, 5 deliberate.

| Member | Finding | Verdict |
|---|---|---|
| `ValidateModAndFileData` | NIT's Validate Mods first resyncs the database with the mod folders: it adds unknown mod folders (to Ungrouped) and new installer files, drops records of deleted or mis-grouped files, relinks records, then refreshes every file and mod state. VK did none of it. Ported (`ProfileData.validate_mod_and_file_data`). **Deliberate:** NIT also removes every mod whose folder is gone; on the owner's real profile that would delete 20 of 32 mods, whose imported definitions have no folder, so such mods are kept. A game copy with no checksum is checksummed with its mod file; without this 2,678 records read as "overridden" in the dry run. Real-data dry run (in memory): the orphan folder "Lord Of Destruction" is added; 12 records of installer files that no longer exist are dropped (7 `.nwm` + a `.nitres` in "1. Neverwinter Nights (EE)", whose folder holds only a `.nitins`, and 4 in two Auto restorers). | MISSING → fixed |
| `CheckSelectedFiles`, `AddDatabaseFiles`, `CheckAutoFileChanges` | On game exit (and window activation) NIT records new and changed database files and vault journals, so the auto restorers back them up at once. VK's restorers only saw files already in the records, so a database created while playing waited for the next profile open. `record_play_files` now runs first in `run_auto_restorers`. | BUG → fixed |
| `AddCrashDumpFiles` + `CrashDumpManager` | New `nwmain-crash-*` reports after play, with a manager to open or delete them. Missing in VK; ported (`game/crash_reports.py`, `CrashReportsDialog`, `show_crash_file_manager`). | MISSING → fixed |
| `ValidateNotes` | Also run when a profile loads, as in NIT. | fixed |
| `IsIllegalFile`, `ValidInstalled*` | NIT exempts `.log` anywhere, `.json` in mod/nwm, images in ovr/mod, patch-INI backups and a few names. VK's Validate Neverwinter Nights flagged them all; on the owner's install it offered to delete `mod/repository.json`, `nwm/repository.json` and the save editor's own `vk_*.json` manifests (which track the haks it wrote). Exceptions added, `vk_*.json` included. | BUG → fixed |
| `UpdateOriginalEeFilesThread` | VK learned whatever file sat in the folder, so a file a mod had installed over an original became the new "original" (and a later original restorer would back up the mod's copy). NIT keeps the known CRC for installer-owned files and takes a default restorer's copy CRC. | BUG → fixed |
| `SaveEeFileVersion` / `NIT.ProfileView` | NIT reruns Update EE Files on load when the game executable changed. Ported with per-profile executable CRCs. **Deliberate:** the first sighting only records the CRC. On the owner's install the 15 campaign `.nwm` files were changed on 14–15 Aug outside any mod (the PRC-ified campaign), so learning now would make them the "originals". | MISSING → fixed |
| `OriginalSourceFile` | A file held by one of the three original restorers whose copy is stale is backed up again in NIT; VK skipped it. | fixed |
| `UpdateDatabaseFile` | NIT does not count an SQLite file that EE rewrote at the same length as changed; VK re-checksums it, so the Auto restorer may take one extra copy. | deliberate (harmless) |
| `LoadSelections` / `SaveSelections` | NIT restores the selected mod/contents/details per profile across restarts; VK does not. | deliberate (UI state; screen-parity phase) |
| `BuildOriginalFiles` | Classic: NIT can rescan a Diamond install; VK uses the bundled 1.69 table. | deliberate |
| `GroupMemberData.Rename` | NIT clears the removed list and calls `ResetModFiles` + `FindInstaller` itself; VK re-resolves the removed keys in `update_file_states`, giving the same owners. | same |

Regression tests: `tests/test_validate_mod_data_parity.py`, `tests/test_crash_reports.py`,
`tests/test_auto_restorers.py::test_files_written_while_playing_are_backed_up_straight_away`,
`tests/test_validate_nwn.py::test_files_nit_allows_are_not_reported`,
`tests/test_update_ee_files.py` (last two), `tests/test_original_files.py::test_original_source_files_includes_a_stale_original_restorer_copy`,
`tests/test_notes_parity.py::test_orphaned_notes_are_recycled_when_the_profile_opens`.

## Batch 3 — Paths, ProfileInfo, ProfileInfoManager, NwnFolderInfo

111 verdicts: 83 same, 13 n/a, 8 fixed, 7 deliberate. Most of Paths.vb is
one-line path properties that map onto the store layout.

| Member | Finding | Verdict |
|---|---|---|
| `SetGameSavesPath` | NIT (and the game) find saves through `nwn.ini`'s `SAVES` alias. VK hard-coded `<user>/saves` for the Game Saves Manager, play-session save tracking, the saves count and the character list. The owner's alias points at `saves___` and `saves` is empty, so VK showed none of their 11 saves, and Reduce/Archive had nothing to act on. Now `game_saves_dir()` / `nwn_folders.saves_folder()`. | BUG → fixed |
| `PopulateLocations` / `ValidateNwnIni` | On every load NIT points each alias at the same-named sub-folder of the profile's own user folder, and HD0 at the folder. A user folder copied for a test profile keeps the original's absolute aliases, so under VK the game, and every install for the test profile, used the live folder. VK now detects this before the profile opens (opening checks, and anneals, the folders it resolves) and repoints the aliases if the user agrees (`nwn.ini.bak` kept). It leaves CD0, SAVES, NWMFILES, relative values and other-OS values alone. The owner's `nwn.ini` needs nothing. Asking, not writing silently, is deliberate (VK's rule for game config; 3a F3). | MISSING → fixed |
| `UserRulesFile` | NIT appends `User Rules.txt` (store Data folder) to the download rules, e.g. to add private projects to NoInstallerProjects. VK had no such file. It is now created with an explanatory header, appended on load, and opened for editing by the rules-file menu command. | MISSING → fixed |
| `SteamLibrary` | NIT reads Steam's `libraryfolders.vdf` and accepts a "Neverwinter Nights Enhanced Edition" install folder; VK searched only the default library, so a game on a second drive was never found (nwn-save-editor `6e34bff`). | MISSING → fixed |
| `SetGameSaves` | NIT's shared saves-folder setting rewrites `SAVES` in every profile's `nwn.ini`; VK has no such setting (edit the alias instead). | deliberate |
| Custom alias definitions | NIT can keep per-profile custom alias locations and reapply them; VK's Alias editor edits `nwn.ini` directly. | deliberate |
| `GetProfiles`, `Validate` | NIT re-adopts profiles that exist only in Data, falls back to the default/first profile when the active one's folder is gone, and disables profiles whose game folder is missing. VK lists Profiles sub-folders and recreates a missing folder on open; no data is lost either way. | deliberate (noted) |
| `CheckAccessPermissions` | NIT probes read/write access up front; VK reports write errors where they happen. | deliberate |
| `OperationStates` | One-time NIT data migrations. `UpdateEeFiles` is covered by batch 2's executable check; the hak-patch refresh on load goes to batch 4. | n/a |
| `ValidateNwnConfigIni` | Classic only: rewrites `nwnconfig.ini`'s `[Registry]` paths for a moved Diamond install. | n/a |

Regression tests: `tests/test_alias_repair.py`, `tests/test_rules_source.py`,
`tests/test_ui_main_window.py` (rules-file command), nwn-save-editor
`tests/test_steam_libraries.py`.
