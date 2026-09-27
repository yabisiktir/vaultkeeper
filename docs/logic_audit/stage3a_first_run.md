# Stage 3a — first run, profiles, INI

Method: the "00 start" snapshot of every stage-2 run is each app's state right
after its own first run on identical sandboxes (NIT answers its six first-run
questions from `harness/dialog_rules.tsv`); profile switch, rename and delete
compared by reading NIT (`NIT.ProfileView.vb`, `Settings.Profiles.vb`) against
`ui/session.py`, with Vaultkeeper scenario tests.

## NIT's first-run questions

| # | NIT question | Vaultkeeper | Verdict |
|---|---|---|---|
| 1 | Create the missing Profiles sub-folder? | created silently | same effect |
| 2 | Alias Section of nwn.ini changed (adds `NWMFiles`, `SOURCEOVERRIDE`, `PATCH`) | nwn.ini untouched | **F3 — DELIBERATE, VK better.** NIT writes them so its *own* folder table (`PopulateLocations`) can read the EE library paths back; the game does not use them and a real EE nwn.ini lacks them. VK derives those folders itself. Writing absolute paths into the user's nwn.ini is what breaks a user folder shared by two OSes. |
| 3 | Mod Player or Builder? | `offer_player_excludes` | same |
| 4 | Group Set for EE Mods | first-run screen `group_set` | same |
| 5 | Create Restorers for files installed by NWN? | **not asked** (menu command only) | **F1 — BUG, fixed** |
| 6 | Apply Theme colours to Notes (RTF)? | not asked | N/A: NIT rewrites the colours inside the users' RTF files; VK shows notes in the theme without changing them |

## Findings

| ID | Finding | Verdict |
|---|---|---|
| F1 ✅ | NIT asks, when a profile is new or migrated, whether to back up the files NWN installed (with the disk space needed). VK only had the menu command. Now asked after the first-run questions (`MainWindow.offer_original_restorers`, `ProfileController.original_restorers_offer`). | BUG → fixed |
| F1b ✅ | The original restorers were grouped differently: VK made one restorer per module file ("Chapter1", "Chapter1E", "XP1-Chapter 1"… ~26 on EE), without the edition. NIT makes one per campaign ("1. Neverwinter Nights (EE)", "2. The Shadow of Undrentide (EE)", "3. Hordes of the Underdark (EE)"), one per bundled module (Contest of Champions, demos, premium modules with the "Neverwinter Nights - " prefix dropped, EE `mod` modules), and counts a classic non-bundled `.mod` as a core file. `restorer_buckets` now ports `AutoOriginalRestorer` + `IsNotNamedOriginal`. Deliberate difference kept: with no Restorers group NIT uses No Group; VK creates the group, so restorers keep their intended priority (ungrouped mods are the lowest). | BUG → fixed |
| F2 | NIT creates an empty `userpatch.ini` (and `.bak`) at first run; VK creates it at the first install. The game treats a missing file as empty. NIT's INI restorer then backs up that empty file NIT made itself. | harmless |
| P1 ✅ | **Profiles were not checked against the game when opened.** NIT runs `CheckInstalledFiles` on every load (start-up and every profile switch) and anneals the affected mods; VK only from a menu. A switched-to profile showed what it saw when last closed, though the game folder is shared with other profiles, the game and other tools. Now done in `open_profile` for a saved profile (`_check_game_on_open`), with a note when mods were affected. | BUG → fixed |
| P2 ✅ | `check_installed_files` dropped the record of a vanished file without marking the mods that had it not-installed (VB `RemoveFile`), and did not checksum added/changed files (their CRC read 0, the S3 trap). Both fixed. | BUG → fixed |
| P3 | Profile rename / delete: NIT renames or deletes (recycle) `Profiles\<name>` and `Data\<name>`, undoing a half rename; VK does the same plus its `<name>.json` store and per-profile settings. | same |

Regression tests: `tests/test_first_run_original_restorers.py`,
`tests/test_original_files.py` (NIT grouping), `tests/test_check_game_on_open.py`.
