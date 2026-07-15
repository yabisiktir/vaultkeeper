# NIT → Vaultkeeper parity coverage ledger

Machine-generated denominator of the original VB app, auto-matched against the
Python port. Every row carries a status; the audit is complete when no row is
`GAP?` / `AUTO-PORTED` (i.e. every unit is verified or explicitly categorised).

Regenerate: `python extract_vb.py <vb> ./out && python build_ledger.py ./out <port> .`

## Coverage

| Layer | Total | Accounted | Machine queue (AUTO-PORTED + GAP?) |
|---|---|---|---|
| Methods/props | 3284 | 1461 (44%) | 1823 |
| Event handlers | 885 | 508 (57%) | 377 |
| Designer controls | 1777 | 42 (2%) | 1735 |

### Methods/props — status breakdown
- `GAP?`: 1082
- `AUTO-PORTED`: 741
- `Divergence`: 636
- `Ported`: 372
- `N/A`: 188
- `Deferred`: 177
- `Partial`: 85
- `MISSING`: 3

### Event handlers — status breakdown
- `GAP?`: 370
- `Divergence`: 311
- `Ported`: 106
- `Deferred`: 67
- `Partial`: 22
- `AUTO-PORTED`: 7
- `MISSING`: 2

### Designer controls — status breakdown
- `GAP?`: 1432
- `AUTO-PORTED`: 303
- `Deferred`: 25
- `Divergence`: 17

## Where to look — GAP? density by VB file (methods)

Files with the most unmatched methods surface first; these are the sweep priorities.

| VB file | methods | GAP? | AUTO-PORTED | accounted |
|---|---|---|---|---|
| NIT.Menu.vb | 228 | 100 | 13 | 115 |
| InstallationManagerEditor.vb | 39 | 29 | 1 | 9 |
| Settings.Classes.vb | 71 | 25 | 20 | 26 |
| Settings.vb | 27 | 21 | 2 | 4 |
| Settings.Config.vb | 20 | 20 | 0 | 0 |
| BackupManager.vb | 33 | 20 | 3 | 10 |
| NetworkManager.vb | 24 | 19 | 4 | 1 |
| MsgPicture.vb | 22 | 19 | 1 | 2 |
| InstallationAnalyser.vb | 28 | 19 | 1 | 8 |
| ProfileData.Properties.vb | 34 | 18 | 15 | 1 |
| PlayDataViewer.vb | 19 | 18 | 0 | 1 |
| InstallationManager.vb | 29 | 18 | 7 | 4 |
| MenuItemEditor.vb | 23 | 17 | 1 | 5 |
| NIT.ModView.vb | 59 | 16 | 10 | 33 |
| ModFindAndRename.ModNames.vb | 25 | 16 | 7 | 2 |
| FindProfileFilesDialogue.vb | 24 | 16 | 2 | 6 |
| StartScreenInfo.vb | 42 | 15 | 24 | 3 |
| SlideShow.vb | 18 | 15 | 0 | 3 |
| Settings.MapExtensions.vb | 15 | 15 | 0 | 0 |
| Settings.MapExcludes.vb | 15 | 15 | 0 | 0 |
| Settings.Profiles.vb | 15 | 14 | 0 | 1 |
| Settings.Locations.vb | 14 | 14 | 0 | 0 |
| HakPatchManager.vb | 26 | 14 | 11 | 1 |
| FileConflictsViewer.vb | 19 | 14 | 0 | 5 |
| Settings.MapFolders.vb | 13 | 13 | 0 | 0 |
| RtfThemeManager.vb | 14 | 13 | 1 | 0 |
| NIT.Paste.vb | 18 | 13 | 2 | 3 |
| NIT.DetailsView.vb | 14 | 13 | 1 | 0 |
| SteamWorkshop.vb | 22 | 12 | 7 | 3 |
| Settings.Advanced.vb | 12 | 12 | 0 | 0 |

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
| AliasSectionEditor.vb:326 | AliasSectionEditor | LvFolders_SelectedIndexChanged | Sub |
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
| BackupManager.Methods.vb:24 | BackupManager | DisplaySelectionInfo | Sub |
| BackupManager.Methods.vb:93 | BackupManager | PopulateStandard | Function |
| BackupManager.Methods.vb:118 | BackupManager | UpdateListView | Sub |
| BackupManager.Methods.vb:180 | BackupManager | DeleteFiles | Sub |
| BackupManager.Methods.vb:197 | BackupManager | DeleteMods | Sub |
| BackupManager.Methods.vb:219 | BackupManager | RemoveItems | Sub |
| BackupManager.TypeInfo.vb:45 | TypeInfo | DataType | Property |
| BackupManager.TypeInfo.vb:55 | TypeInfo | ActionAllowed | Property |
| BackupManager.TypeInfo.vb:60 | TypeInfo | ActionText | Property |
| BackupManager.TypeInfo.vb:65 | TypeInfo | DeleteText | Property |
| BackupManager.vb:28 | BackupManager | ActionType | Property |
| BackupManager.vb:35 | BackupManager | ActionItem | Property |
| BackupManager.vb:40 | BackupManager | ActionText | Property |
| BackupManager.vb:52 | BackupManager | DataInfo | Property |
| BackupManager.vb:121 | BackupManager | AutoImport | Property |
| BackupManager.vb:126 | BackupManager | Initialising | Property |
| BackupManager.vb:136 | BackupManager | SelectedSize | Property |
| BackupManager.vb:160 | BackupManager | TabPage | Property |
| BackupManager.vb:214 | BackupManager | BackupManager_Load | Sub |
| BackupManager.vb:317 | BackupManager | BackupManager_Shown | Sub |
| BackupManager.vb:342 | BackupManager | BhBackupManager_Click | Sub |
| BackupManager.vb:360 | BackupManager | BtAction_SizeChanged | Sub |
| BackupManager.vb:368 | BackupManager | BtAction_Click | Sub |
| BackupManager.vb:385 | BackupManager | BackupManager_KeyUp | Sub |
| BackupManager.vb:448 | BackupManager | TbBackupManager_SelectedIndexChanged | Sub |
| BackupManager.vb:558 | BackupManager | BgBackups_DoWork | Sub |
| BackupManager.vb:568 | BackupManager | BgSettings_DoWork | Sub |
| BackupManager.vb:580 | BackupManager | BgStandard_ProgressChanged | Sub |
| BackupManager.vb:590 | BackupManager | BgMods_DoWork | Sub |
| BackupManager.vb:622 | BackupManager | BgMods_ProgressChanged | Sub |
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

_(1082 GAP? methods total; see ledger_members.csv for the full list.)_

## Findings (confirmed divergences)

These are real divergences confirmed against the VB source during audit design
(2026-07-15). They demonstrate the ledger catches behavior/layout/depth gaps that
the command-level audit did not.

1. **Empty groups not rendered for drag-drop** — `NIT.ModView.vb:69` `ApplyGroupsAndStatus` loops every `pd.Groups.Values` and calls `FvMods.AddGroup` for each, so empty groups still render (enabling drag-into-empty-group). The port's `FileView.populate` only emits groups that have members. → behavior gap.
2. **Ribbon tabs centered, not left-aligned** — `TbRibbon` is a WinForms `TabControl` (tabs left-packed); the port centers them. → designer-property gap.
3. **Settings depth (content gap, not just form)** — VB exposes 181 `My.Settings.*` keys; stripping Map/Colour/Path/Private internals leaves ~40-50 real user preferences (`Behaviour*`/`Config*`/`File*`), of which the port's settings model holds only ~10. Some map to ported features under other names, but genuinely-unmodelled ones include `ConfigMaxCrcThreads`, `ConfigPortraitDisplaySize`, `BehaviourSelectGameMod`, `ConfigDefaultGroup`, `ConfigSavesRetention`, `FilterSkillsByRank`. → run the Settings sub-sweep (enumerate every pref key, classify, build the missing ones).

