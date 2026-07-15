# NIT → Vaultkeeper parity coverage ledger

Machine-generated denominator of the original VB app, auto-matched against the
Python port. Every row carries a status; the audit is complete when no row is
`GAP?` / `AUTO-PORTED` (i.e. every unit is verified or explicitly categorised).

Regenerate: `python extract_vb.py <vb> ./out && python build_ledger.py ./out <port> .`

## Coverage

| Layer | Total | Accounted | Machine queue (AUTO-PORTED + GAP?) |
|---|---|---|---|
| Methods/props | 3284 | 2579 (78%) | 705 |
| Event handlers | 885 | 845 (95%) | 40 |
| Designer controls | 1777 | 42 (2%) | 1735 |

### Methods/props — status breakdown
- `Divergence`: 1256
- `AUTO-PORTED`: 561
- `Ported`: 548
- `Deferred`: 423
- `N/A`: 188
- `Partial`: 161
- `GAP?`: 144
- `MISSING`: 3

### Event handlers — status breakdown
- `Divergence`: 522
- `Deferred`: 146
- `Ported`: 132
- `Partial`: 43
- `GAP?`: 33
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
| Settings.WebMenu.vb | 8 | 7 | 1 | 0 |
| ProfileInfo.vb | 15 | 7 | 2 | 6 |
| NitDownload.vb | 9 | 7 | 0 | 2 |
| ProfileDataExtensions.vb | 9 | 6 | 3 | 0 |
| FindDialogue.vb | 15 | 6 | 2 | 7 |
| ApplicationEvents.vb | 6 | 6 | 0 | 0 |
| VaultDownloadRules.ProjectInfo.vb | 11 | 5 | 3 | 3 |
| SteamWorkshop.IdInfo.vb | 15 | 5 | 6 | 4 |
| ModExport.vb | 11 | 5 | 3 | 3 |
| InstallationManager.SetInfo.vb | 16 | 5 | 6 | 5 |
| ErfFileReader.IfoReader.vb | 6 | 5 | 0 | 1 |
| DownloadDeleteMsg.vb | 9 | 5 | 1 | 3 |
| CharacterFilter.vb | 11 | 5 | 2 | 4 |
| CalculateCRCs.CrcInfo.vb | 12 | 5 | 6 | 1 |
| BikToWbmDialogue.vb | 16 | 5 | 4 | 7 |
| BicFileInfo.vb | 17 | 5 | 10 | 2 |
| WorkshopNameEditor.vb | 11 | 4 | 2 | 5 |
| Settings.MapCommon.vb | 4 | 4 | 0 | 0 |
| DailyPlayTimeInfo.vb | 8 | 4 | 2 | 2 |
| SteamWorkshop.ModInfo.vb | 11 | 3 | 5 | 3 |
| ProfileData.Config.vb | 8 | 3 | 3 | 2 |
| GroupMemberData.vb | 14 | 3 | 8 | 3 |
| GameMapper.Workers.vb | 5 | 3 | 2 | 0 |
| FileKeyInfo.vb | 31 | 3 | 13 | 15 |
| DocOrganiser.ProcessDocs.vb | 5 | 3 | 2 | 0 |
| VaultScraperInfo.vb | 19 | 2 | 11 | 6 |
| ProfileData.vb | 81 | 2 | 32 | 47 |
| PlayTimeInfo.vb | 14 | 2 | 1 | 11 |
| PlayDataViewPending.vb | 3 | 2 | 0 | 1 |
| ModExplorerExtensions.vb | 3 | 2 | 0 | 1 |

## Work queue — GAP? methods (no port match; investigate)

First 60 shown. A `GAP?` means the auto-matcher found no name/comment hit in the
port — it is a *candidate* miss to confirm, not a proven gap (the port may
implement it under a different name).

| VB ref | class | method | kind |
|---|---|---|---|
| ApplicationEvents.vb:28 | MyApplication | MyApplication_Startup | Sub |
| ApplicationEvents.vb:65 | MyApplication | MyApplication_UnhandledException | Sub |
| ApplicationEvents.vb:156 | MyApplication | LogExceptionInfo | Sub |
| ApplicationEvents.vb:196 | MyApplication | MyApplication_StartupNextInstance | Sub |
| ApplicationEvents.vb:217 | MyApplication | RestartOnShutdown | Property |
| ApplicationEvents.vb:219 | MyApplication | MyApplication_Shutdown | Sub |
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
| CommonFiltersDialogue.vb:62 | CommonFiltersDialogue | Filters_Load | Sub |
| DailyPlayTimeInfo.vb:89 | DailyPlayTimeInfo | TodaysTime | Sub |
| DailyPlayTimeInfo.vb:109 | DailyPlayTimeInfo | NitStartUp | Sub |
| DailyPlayTimeInfo.vb:128 | DailyPlayTimeInfo | DailyAverage | Function |
| DailyPlayTimeInfo.vb:185 | DailyPlayTimeInfo | GetDailyPlayInfo | Function |
| DocOrganiser.ProcessDocs.vb:157 | DocOrganiser | BgProcessDocs_ProgressChanged | Sub |
| DocOrganiser.ProcessDocs.vb:197 | DocOrganiser | BgProcessDocs_RunWorkerCompleted | Sub |
| DocOrganiser.ProcessDocs.vb:315 | DocOrganiser | RestoreDocInfo | Sub |
| DownloadDeleteMsg.vb:68 | DownloadDeleteMsg | MarkedFileCount | Property |
| DownloadDeleteMsg.vb:87 | DownloadDeleteMsg | CheckedFileCount | Property |
| DownloadDeleteMsg.vb:105 | DownloadDeleteMsg | DownloadDeleteMsg_Load | Sub |
| DownloadDeleteMsg.vb:127 | DownloadDeleteMsg | LvFileList_ItemChecked | Sub |
| DownloadDeleteMsg.vb:146 | DownloadDeleteMsg | BtHistory_Click | Sub |
| ErfFileReader.IfoReader.vb:62 | IfoReader | GetFieldText | Function |
| ErfFileReader.IfoReader.vb:122 | IfoReader | ReadHeader | Function |
| ErfFileReader.IfoReader.vb:152 | IfoReader | GetFieldDataCExoLocString | Function |
| ErfFileReader.IfoReader.vb:178 | IfoReader | GetLabel | Function |
| ErfFileReader.IfoReader.vb:189 | IfoReader | IsIfoHeader | Function |
| FileKeyInfo.vb:248 | FileKeyInfo | CrashReportFullName | Property |
| FileKeyInfo.vb:367 | EqualityComparer | IEqualityComparer_Equals | Function |
| FileKeyInfo.vb:372 | EqualityComparer | IEqualityComparer_GetHashCode | Function |
| FindDialogue.vb:85 | FindDialogue | FindDialogue_Load | Sub |
| FindDialogue.vb:137 | FindDialogue | FindDialogue_Shown | Sub |
| FindDialogue.vb:192 | FindDialogue | SetFindButtonAvailibility | Sub |
| FindDialogue.vb:203 | FindDialogue | BtFindNext_Click | Sub |
| FindDialogue.vb:213 | FindDialogue | BtFindPrevious_Click | Sub |
| FindDialogue.vb:269 | FindDialogue | ItemFound | Sub |
| GameMapper.Defs.vb:109 | GameMapper | UserResponsesFile | Property |
| GameMapper.Internal.vb:106 | GameMapper | GetDescriptionFromFile | Function |
| GameMapper.Internal.vb:297 | GameMapper | GetSaveInfo | Function |
| GameMapper.UserResponses.vb:258 | UserResponses | PopulateListView | Sub |
| GameMapper.UserResponses.vb:313 | UserResponses | UpdateFromListView | Sub |
| GameMapper.Workers.vb:27 | GameMapper | BgModScanner_DoWork | Sub |
| GameMapper.Workers.vb:55 | GameMapper | BgModScanner_ProgressChanged | Sub |

_(144 GAP? methods total; see ledger_members.csv for the full list.)_

## Findings (confirmed divergences)

These are real divergences confirmed against the VB source during audit design
(2026-07-15). They demonstrate the ledger catches behavior/layout/depth gaps that
the command-level audit did not.

1. **Empty groups not rendered for drag-drop** — `NIT.ModView.vb:69` `ApplyGroupsAndStatus` loops every `pd.Groups.Values` and calls `FvMods.AddGroup` for each, so empty groups still render (enabling drag-into-empty-group). The port's `FileView.populate` only emits groups that have members. → behavior gap.
2. **Ribbon tabs centered, not left-aligned** — `TbRibbon` is a WinForms `TabControl` (tabs left-packed); the port centers them. → designer-property gap.
3. **Settings depth (content gap, not just form)** — VB exposes 181 `My.Settings.*` keys; stripping Map/Colour/Path/Private internals leaves ~40-50 real user preferences (`Behaviour*`/`Config*`/`File*`), of which the port's settings model holds only ~10. Some map to ported features under other names, but genuinely-unmodelled ones include `ConfigMaxCrcThreads`, `ConfigPortraitDisplaySize`, `BehaviourSelectGameMod`, `ConfigDefaultGroup`, `ConfigSavesRetention`, `FilterSkillsByRank`. → run the Settings sub-sweep (enumerate every pref key, classify, build the missing ones).

