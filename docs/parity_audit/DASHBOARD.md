# NIT → Vaultkeeper parity coverage ledger

Machine-generated denominator of the original VB app, auto-matched against the
Python port. Every row carries a status; the audit is complete when no row is
`GAP?` / `AUTO-PORTED` (i.e. every unit is verified or explicitly categorised).

Regenerate: `python extract_vb.py <vb> ./out && python build_ledger.py ./out <port> .`

## Coverage

| Layer | Total | Accounted | Machine queue (AUTO-PORTED + GAP?) |
|---|---|---|---|
| Methods/props | 3284 | 2350 (71%) | 934 |
| Event handlers | 885 | 753 (85%) | 132 |
| Designer controls | 1777 | 42 (2%) | 1735 |

### Methods/props — status breakdown
- `Divergence`: 1104
- `AUTO-PORTED`: 561
- `Ported`: 536
- `GAP?`: 373
- `Deferred`: 370
- `N/A`: 188
- `Partial`: 149
- `MISSING`: 3

### Event handlers — status breakdown
- `Divergence`: 464
- `Ported`: 132
- `GAP?`: 125
- `Deferred`: 114
- `Partial`: 41
- `AUTO-PORTED`: 7
- `MISSING`: 2

### Designer controls — status breakdown
- `GAP?`: 1426
- `AUTO-PORTED`: 309
- `Deferred`: 25
- `Divergence`: 17

## Where to look — GAP? density by VB file (methods)

Files with the most unmatched methods surface first; these are the sweep priorities.

| VB file | methods | GAP? | AUTO-PORTED | accounted |
|---|---|---|---|---|
| NIT.ModView.vb | 59 | 16 | 8 | 35 |
| Settings.Advanced.vb | 12 | 12 | 0 | 0 |
| GameManager.GameManagerInfo.vb | 23 | 12 | 5 | 6 |
| ExtendedEditionDialogue.vb | 18 | 12 | 1 | 5 |
| Settings.MenuCommon.vb | 13 | 11 | 0 | 2 |
| ModExplorer.Properties.vb | 15 | 11 | 4 | 0 |
| GameManagerRestore.vb | 19 | 11 | 0 | 8 |
| GameManager.Methods.vb | 16 | 11 | 5 | 0 |
| Settings.Preferences.vb | 10 | 10 | 0 | 0 |
| Settings.Common.vb | 15 | 10 | 1 | 4 |
| ModExplorer.ListManager.vb | 11 | 10 | 0 | 1 |
| CrashDumpManager.vb | 18 | 10 | 2 | 6 |
| AliasSectionEditor.vb | 15 | 10 | 0 | 5 |
| Settings.MapExceptions.vb | 9 | 9 | 0 | 0 |
| HakPatchEditor.vb | 11 | 9 | 1 | 1 |
| GameSaves.vb | 25 | 9 | 9 | 7 |
| ClassesSkillsAndFeats.vb | 15 | 9 | 3 | 3 |
| BasicSettings.vb | 11 | 9 | 0 | 2 |
| Settings.RunMenu.vb | 8 | 8 | 0 | 0 |
| ModExplorer.Common.vb | 9 | 8 | 1 | 0 |
| DependencyManager.vb | 14 | 8 | 0 | 6 |
| Settings.WebMenu.vb | 8 | 7 | 1 | 0 |
| ProfileInfo.vb | 15 | 7 | 2 | 6 |
| NitDownload.vb | 9 | 7 | 0 | 2 |
| GameSavesPathDialogue.vb | 11 | 7 | 0 | 4 |
| DownloadProject.Properties.vb | 9 | 7 | 2 | 0 |
| ProfileDataExtensions.vb | 9 | 6 | 3 | 0 |
| FindDialogue.vb | 15 | 6 | 2 | 7 |
| ApplicationEvents.vb | 6 | 6 | 0 | 0 |
| VaultDownloadRules.ProjectInfo.vb | 11 | 5 | 3 | 3 |

## Work queue — GAP? methods (no port match; investigate)

First 60 shown. A `GAP?` means the auto-matcher found no name/comment hit in the
port — it is a *candidate* miss to confirm, not a proven gap (the port may
implement it under a different name).

| VB ref | class | method | kind |
|---|---|---|---|
| AliasSectionEditor.vb:61 | AliasSectionEditor | AliasSectionEditor_Load | Sub |
| AliasSectionEditor.vb:148 | AliasSectionEditor | AliasSectionEditor_Shown | Sub |
| AliasSectionEditor.vb:159 | AliasSectionEditor | BhAliasEditor_Click | Sub |
| AliasSectionEditor.vb:192 | AliasSectionEditor | RestoreDefaults | Sub |
| AliasSectionEditor.vb:298 | AliasSectionEditor | LvFolders_ItemClicked | Sub |
| AliasSectionEditor.vb:341 | AliasSectionEditor | CmMenuItem_Click | Sub |
| AliasSectionEditor.vb:359 | AliasSectionEditor | ChangeFolder | Sub |
| AliasSectionEditor.vb:432 | AliasSectionEditor | RestoreFolder | Sub |
| AliasSectionEditor.vb:452 | AliasSectionEditor | RefreshContextMenu | Sub |
| AliasSectionEditor.vb:467 | AliasSectionEditor | SavesTypeSuffix | Sub |
| ApplicationEvents.vb:28 | MyApplication | MyApplication_Startup | Sub |
| ApplicationEvents.vb:65 | MyApplication | MyApplication_UnhandledException | Sub |
| ApplicationEvents.vb:156 | MyApplication | LogExceptionInfo | Sub |
| ApplicationEvents.vb:196 | MyApplication | MyApplication_StartupNextInstance | Sub |
| ApplicationEvents.vb:217 | MyApplication | RestartOnShutdown | Property |
| ApplicationEvents.vb:219 | MyApplication | MyApplication_Shutdown | Sub |
| BasicSettings.vb:29 | BasicSettings | BasicSettings_Load | Sub |
| BasicSettings.vb:90 | BasicSettings | CbCommon_CheckedChanged | Sub |
| BasicSettings.vb:103 | BasicSettings | CbCopyDebugModeOnPlay_CheckedChanged | Sub |
| BasicSettings.vb:129 | BasicSettings | CbInstallRestore_CheckedChanged | Sub |
| BasicSettings.vb:141 | BasicSettings | PicCheckBox_Click | Sub |
| BasicSettings.vb:151 | BasicSettings | RbLine_CheckedChanged | Sub |
| BasicSettings.vb:166 | BasicSettings | BhBasicSettings_Click | Sub |
| BasicSettings.vb:176 | BasicSettings | BtSelection_Click | Sub |
| BasicSettings.vb:184 | BasicSettings | BtAdvanced_Click | Sub |
| BicFileInfo.vb:157 | BicFileInfo | SkillInfo | Property |
| BicFileInfo.vb:186 | BicFileInfo | PlayerFeats | Property |
| BicFileInfo.vb:444 | BicFileInfo | DisplayCharacterInformation | Sub |
| BicFileInfo.vb:457 | BicFileInfo | SkillDescription | Function |
| BicFileInfo.vb:473 | BicFileInfo | FeatDescription | Function |
| BikToWbmDialogue.vb:35 | BikToWbmDialogue | FileCount | Property |
| BikToWbmDialogue.vb:54 | BikToWbmDialogue | IncompleteMods | Property |
| BikToWbmDialogue.vb:81 | BikToWbmDialogue | BikToWbmDialogue_Load | Sub |
| BikToWbmDialogue.vb:99 | BikToWbmDialogue | BikToWbmDialogue_Shown | Sub |
| BikToWbmDialogue.vb:110 | BikToWbmDialogue | BikToWbmDialogue_FormClosing | Sub |
| CalculateCRCs.CrcInfo.vb:50 | CrcInfo | BgIndex | Property |
| CalculateCRCs.CrcInfo.vb:100 | CrcInfo | DisplayFolder | Property |
| CalculateCRCs.CrcInfo.vb:108 | CrcInfo | CrcValue | Property |
| CalculateCRCs.CrcInfo.vb:124 | CrcInfo | CrcStatus | Property |
| CalculateCRCs.CrcInfo.vb:132 | CrcInfo | CrcError | Property |
| CharacterFilter.vb:53 | CharacterFilter | ClassNamesFilter | Property |
| CharacterFilter.vb:59 | CharacterFilter | CharacterFilter_Load | Sub |
| CharacterFilter.vb:101 | CharacterFilter | CharacterFilter_Shown | Sub |
| CharacterFilter.vb:149 | CharacterFilter | LvClassNames_ItemClicked | Sub |
| CharacterFilter.vb:161 | CharacterFilter | LvClassNames_ItemCheck | Sub |
| ClassesSkillsAndFeats.vb:27 | ClassesSkillsAndFeats | ErrorText | Property |
| ClassesSkillsAndFeats.vb:159 | ClassesSkillsAndFeats | SkillsAndFeats_Shown | Sub |
| ClassesSkillsAndFeats.vb:177 | ClassesSkillsAndFeats | TabMain_SelectedIndexChanged | Sub |
| ClassesSkillsAndFeats.vb:197 | ClassesSkillsAndFeats | LvClasses_RetrieveVirtualItem | Sub |
| ClassesSkillsAndFeats.vb:208 | ClassesSkillsAndFeats | LvClasses_SelectedIndexChanged | Sub |
| ClassesSkillsAndFeats.vb:237 | ClassesSkillsAndFeats | LvSkills_SelectedIndexChanged | Sub |
| ClassesSkillsAndFeats.vb:263 | ClassesSkillsAndFeats | LvFeats_SelectedIndexChanged | Sub |
| ClassesSkillsAndFeats.vb:291 | ClassesSkillsAndFeats | ActivateSearch | Sub |
| ClassesSkillsAndFeats.vb:341 | ClassesSkillsAndFeats | LoadInfoFiles | Function |
| CommonFiltersDialogue.vb:62 | CommonFiltersDialogue | Filters_Load | Sub |
| CrashDumpManager.vb:52 | DumpInfo | DisplayText | Property |
| CrashDumpManager.vb:93 | CrashDumpManager | CrashFilesDeleted | Property |
| CrashDumpManager.vb:98 | CrashDumpManager | FileSizeAdjustment | Property |
| CrashDumpManager.vb:143 | CrashDumpManager | CrashDumpManager_Load | Sub |
| CrashDumpManager.vb:203 | CrashDumpManager | CrashDumpManager_FormClosing | Sub |

_(373 GAP? methods total; see ledger_members.csv for the full list.)_

## Findings (confirmed divergences)

These are real divergences confirmed against the VB source during audit design
(2026-07-15). They demonstrate the ledger catches behavior/layout/depth gaps that
the command-level audit did not.

1. **Empty groups not rendered for drag-drop** — `NIT.ModView.vb:69` `ApplyGroupsAndStatus` loops every `pd.Groups.Values` and calls `FvMods.AddGroup` for each, so empty groups still render (enabling drag-into-empty-group). The port's `FileView.populate` only emits groups that have members. → behavior gap.
2. **Ribbon tabs centered, not left-aligned** — `TbRibbon` is a WinForms `TabControl` (tabs left-packed); the port centers them. → designer-property gap.
3. **Settings depth (content gap, not just form)** — VB exposes 181 `My.Settings.*` keys; stripping Map/Colour/Path/Private internals leaves ~40-50 real user preferences (`Behaviour*`/`Config*`/`File*`), of which the port's settings model holds only ~10. Some map to ported features under other names, but genuinely-unmodelled ones include `ConfigMaxCrcThreads`, `ConfigPortraitDisplaySize`, `BehaviourSelectGameMod`, `ConfigDefaultGroup`, `ConfigSavesRetention`, `FilterSkillsByRank`. → run the Settings sub-sweep (enumerate every pref key, classify, build the missing ones).

