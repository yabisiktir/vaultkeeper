# Stage 3c — backups and recovery

Method: NIT's handlers (`NIT.Menu.vb` Validate*/Rebuild/Recover/Backup/Restore,
`ProfileData.ValidateInstalledFileData`, `NIT.Common.RestoreData`) compared
branch by branch with `ProfileController`, then scenario tests that damage a
store and run each tool.

| ID | Tool | Finding | Verdict |
|---|---|---|---|
| C1 ✅ | Validate Profile Data | NIT = Validate Installed Data + Validate Mods. VK only pruned dependencies and recomputed states. Now both. | BUG → fixed |
| C2 ✅ | Validate Installed Data | NIT runs `CheckInstalledFiles`, anneals the affected mods, then `ValidateInstalledFileData`: every record's links to vanished mods / mod files are dropped, a vanished file forgotten, a changed or never-checksummed file re-checksummed, an owner that no longer exists re-resolved, an "unknown" file matching a game original relabelled. VK did the first step only. `ProfileData.validate_installed_file_data`. | BUG → fixed |
| C3 ✅ | Restore Data | NIT restores and restarts; the profile load checks the game. VK reloaded the backup and trusted its picture of the game (e.g. a mod installed since the backup showed "not installed"). Now checked after restore. | BUG → fixed |
| C4 | Rebuild Database | NIT recycles the database files and restarts: all groups and mod properties are lost (its own warning). VK rebuilds install state and keeps definitions and groups, with a store backup first (added after VK's own data-loss incident). | VK better |
| C5 | Recover Groups | same rule (create missing groups; move a mod only while it is ungrouped). NIT reads its `.v2` data file or a backup; VK reads its JSON profile or a backup. | same |
| C6 | Backup Data | NIT 7-Zips the Data folder; VK zips it. Same content. | same |

Regression tests: `tests/test_recovery_parity.py` (all 3 fail on the old code).
