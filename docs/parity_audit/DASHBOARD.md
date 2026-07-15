# NIT → Vaultkeeper parity coverage ledger

Machine-generated denominator of the original VB app, auto-matched against the
Python port. Every row carries a status; the audit is complete when no row is
`GAP?` / `AUTO-PORTED` (i.e. every unit is verified or explicitly categorised).

Regenerate: `python extract_vb.py <vb> ./out && python build_ledger.py ./out <port> .`

## Coverage

| Layer | Total | Accounted | Machine queue (AUTO-PORTED + GAP?) |
|---|---|---|---|
| Methods/props | 3284 | 833 (25%) | 2451 |
| Event handlers | 885 | 307 (34%) | 578 |
| Designer controls | 1777 | 42 (2%) | 1735 |

### Methods/props — status breakdown
- `GAP?`: 1584
- `AUTO-PORTED`: 867
- `Divergence`: 338
- `N/A`: 188
- `Ported`: 164
- `Deferred`: 88
- `Partial`: 54
- `MISSING`: 1

### Event handlers — status breakdown
- `GAP?`: 552
- `Divergence`: 185
- `Ported`: 86
- `Deferred`: 29
- `AUTO-PORTED`: 26
- `Partial`: 7

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
| NIT.Common.vb | 95 | 84 | 9 | 2 |
| Defs.vb | 55 | 46 | 7 | 2 |
| InstallationManagerEditor.vb | 39 | 32 | 4 | 3 |
| VaultDownloadRules.vb | 46 | 30 | 15 | 1 |
| NIT.vb | 35 | 29 | 1 | 5 |
| CharacterViewer.vb | 42 | 29 | 9 | 4 |
| ModFindAndRename.vb | 29 | 28 | 1 | 0 |
| WizardBuilder.vb | 34 | 26 | 6 | 2 |
| GameManager.vb | 28 | 26 | 0 | 2 |
| Settings.Classes.vb | 71 | 25 | 24 | 22 |
| NIT.Workers.vb | 26 | 25 | 1 | 0 |
| ModPlayViewer.vb | 45 | 25 | 13 | 7 |
| CreateInstaller.vb | 49 | 25 | 16 | 8 |
| DocOrganiser.vb | 40 | 24 | 13 | 3 |
| BackupManager.vb | 33 | 23 | 5 | 5 |
| Settings.vb | 27 | 22 | 3 | 2 |
| InstallationAnalyser.vb | 28 | 21 | 2 | 5 |
| Settings.Config.vb | 20 | 20 | 0 | 0 |
| NetworkManager.vb | 24 | 19 | 4 | 1 |
| MsgPicture.vb | 22 | 19 | 2 | 1 |
| ProfileData.Properties.vb | 34 | 18 | 16 | 0 |
| PlayDataViewer.vb | 19 | 18 | 0 | 1 |
| InstallationManager.vb | 29 | 18 | 7 | 4 |
| VaultScraper.vb | 28 | 17 | 8 | 3 |
| ModFindAndRename.ModNames.vb | 25 | 17 | 7 | 1 |
| MenuItemEditor.vb | 23 | 17 | 4 | 2 |
| GameManagerRestore.vb | 19 | 17 | 1 | 1 |
| FindProfileFilesDialogue.vb | 24 | 17 | 3 | 4 |
| NIT.ModView.vb | 59 | 16 | 11 | 32 |

## Work queue — GAP? methods (no port match; investigate)

First 60 shown. A `GAP?` means the auto-matcher found no name/comment hit in the
port — it is a *candidate* miss to confirm, not a proven gap (the port may
implement it under a different name).

| VB ref | class | method | kind |
|---|---|---|---|
| AliasSectionEditor.vb:61 | AliasSectionEditor | AliasSectionEditor_Load | Sub |
| AliasSectionEditor.vb:148 | AliasSectionEditor | AliasSectionEditor_Shown | Sub |
| AliasSectionEditor.vb:159 | AliasSectionEditor | BhAliasEditor_Click | Sub |
| AliasSectionEditor.vb:168 | AliasSectionEditor | BtDelete_Click | Sub |
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
| BackupManager.vb:395 | BackupManager | BtDelete_Click | Sub |
| BackupManager.vb:448 | BackupManager | TbBackupManager_SelectedIndexChanged | Sub |
| BackupManager.vb:461 | BackupManager | Lv_SelectedIndexChanged | Sub |
| BackupManager.vb:478 | BackupManager | LvMods_SelectedIndexChanged | Sub |
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

_(1584 GAP? methods total; see ledger_members.csv for the full list.)_

## Findings (confirmed divergences)

These are real divergences confirmed against the VB source during audit design
(2026-07-15). They demonstrate the ledger catches behavior/layout/depth gaps that
the command-level audit did not.

1. **Empty groups not rendered for drag-drop** — `NIT.ModView.vb:69` `ApplyGroupsAndStatus` loops every `pd.Groups.Values` and calls `FvMods.AddGroup` for each, so empty groups still render (enabling drag-into-empty-group). The port's `FileView.populate` only emits groups that have members. → behavior gap.
2. **Ribbon tabs centered, not left-aligned** — `TbRibbon` is a WinForms `TabControl` (tabs left-packed); the port centers them. → designer-property gap.
3. **Settings depth (content gap, not just form)** — VB exposes 181 `My.Settings.*` keys; stripping Map/Colour/Path/Private internals leaves ~40-50 real user preferences (`Behaviour*`/`Config*`/`File*`), of which the port's settings model holds only ~10. Some map to ported features under other names, but genuinely-unmodelled ones include `ConfigMaxCrcThreads`, `ConfigPortraitDisplaySize`, `BehaviourSelectGameMod`, `ConfigDefaultGroup`, `ConfigSavesRetention`, `FilterSkillsByRank`. → run the Settings sub-sweep (enumerate every pref key, classify, build the missing ones).

