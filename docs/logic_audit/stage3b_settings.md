# Stage 3b — settings: defaults and meaning

Method: `stage3/map_settings.py` lists NIT's 184 `My.Settings` values (type,
default, the Settings-page caption from `Settings.Config.vb`) and matches each
to the Vaultkeeper setting whose comment cites it; the rest were mapped by hand.
For every setting that changes behaviour, NIT's consumer (`My.Settings.<Name>`)
was read and compared with Vaultkeeper's.

## Findings

| ID | NIT setting | Finding | Verdict |
|---|---|---|---|
| B1 ✅ | `BehaviourConvertBik` (True) | ported as `convert_bik_files = False`: EE players got `.bik` movies the game cannot play. Now True (settings v3 migration). Also found: with conversion on, a movie that failed to convert (or no converter) was **left out of the installer**; it is now kept as `.bik`. NIT converts only on EE; so does VK now. | BUG → fixed |
| B2 ✅ | `BehaviourSelectGameMod` (True) | ported False. Now True (v3 migration). | BUG → fixed |
| B3 ✅ | `ConfigMinPlayTime` (10 min) | VK recorded any session ≥ 1 min as play. Now 10. | BUG → fixed |
| B4 ✅ | `BehaviourUninstallDeletes` (True) | **Delete** in NIT (`DeleteSelectedMods`): confirm mods others depend on, uninstall installed ones first (checkbox, default on, remembered), delete the mod folders (recycle bin), drop them from dependency lists (`ModDeleted`), anneal the mods that shared their files. VK's Delete only forgot the record: installed files stayed in the game owned by nothing, the folder stayed in the store, nothing was annealed. `ProfileController.delete_mods` + `uninstall_before_delete`. | BUG → fixed |
| B5 ✅ | `BehaviourRetainProperties` (True) | **Import of a mod you already have** (`ImportModsExported`): NIT keeps your group, keeps your rating / best weapon / levels / henchmen / web link, deletes the old folder before copying, uninstalls and reinstalls an installed mod. VK replaced the record wholesale (lost your group and properties), unpacked over the old folder (files the new export dropped lingered), and left the installed copy stale. `retain_properties_on_import` + `import_mods`. | BUG → fixed |
| B6 ✅ | `ConfigDefaultGroup` ("DefaultName") + rules `DefaultGroup` | A downloaded project with no rule group went into the **first group in the list** ("000.  Restorers"). NIT: the existing mod's group, else the rule's, else "810.  Evaluating". `ProfileController.download_group`. | BUG → fixed |
| B7 | `BehaviourMoveAddedMods` (True) | is "Use Move (rather than Copy) when adding files" = VK `use_move_on_add` (True). VK's `move_added_mods` is a separate VK option that had cited the NIT name; comment corrected. | same |
| B8 | `Rules*` (9 toggles) | VK has one toggle (`vault_apply_project_rules`) for all of them. | coarser, not worse |
| B9 | `FileRecycleBinForInstallers` (DeletePermanently) | VK sends replaced installers to the recycle bin. | VK safer |
| B10 | `MapExcludeErf` (True) | VK uses the same default; not user-settable. | same default |
| B11 | `BehaviourDisplayImageFiles` (False→VK True), `FilterSkillsByRank` (True→False), `ConfigSlideShowInterval` (10→5) | viewing preferences only. | UI default, left |
| B12 | `PrivateCheckPlayerExcludes` (True) / `asked_player_excludes` (False) | same meaning, inverted. | same |
| — | 34 `Private*`, window/splitter/colour/font/filter/position settings, thread counts, NIT update and download-speed bookkeeping | no behaviour to compare. | n/a |
| — | `ConfigSavesRetention`, `ConfigSavesThreshold`, `ConfigFlipPortraits`, `ConfigWizardFileThreshold`, `ConfigRunCreateInstaller`, `ConfigRunDocOrganiser`, `FileShowCrashFileManager` | belong to 3c–3i and are checked there. | deferred |

Regression tests: `tests/test_settings_behaviour_parity.py` (6 of its first 7
fail on the old code; the download-group tests were added with B6).
