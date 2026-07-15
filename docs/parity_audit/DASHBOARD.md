# NIT → Vaultkeeper parity coverage ledger

Machine-generated denominator of the original VB app, auto-matched against the
Python port. Every row carries a status; the audit is complete when no row is
`GAP?` / `AUTO-PORTED` (i.e. every unit is verified or explicitly categorised).

Regenerate: `python extract_vb.py <vb> ./out && python build_ledger.py ./out <port> .`

## Coverage

| Layer | Total | Accounted | Machine queue (AUTO-PORTED + GAP?) |
|---|---|---|---|
| Methods/props | 3284 | 2723 (82%) | 561 |
| Event handlers | 885 | 878 (99%) | 7 |
| Designer controls | 1777 | 42 (2%) | 1735 |

### Methods/props — status breakdown
- `Divergence`: 1321
- `Ported`: 603
- `AUTO-PORTED`: 561
- `Deferred`: 446
- `N/A`: 188
- `Partial`: 165

### Event handlers — status breakdown
- `Divergence`: 553
- `Deferred`: 146
- `Ported`: 136
- `Partial`: 43
- `AUTO-PORTED`: 7

### Designer controls — status breakdown
- `GAP?`: 1426
- `AUTO-PORTED`: 309
- `Deferred`: 25
- `Divergence`: 17

## Where to look — GAP? density by VB file (methods)

Files with the most unmatched methods surface first; these are the sweep priorities.

| VB file | methods | GAP? | AUTO-PORTED | accounted |
|---|---|---|---|---|
| WorkshopViewer.vb | 9 | 0 | 0 | 9 |
| WorkshopNameEditor.vb | 11 | 0 | 2 | 9 |
| WizardInfo.vb | 26 | 0 | 24 | 2 |
| WizardBuilder.vb | 34 | 0 | 0 | 34 |
| VaultScraperInfo.vb | 19 | 0 | 11 | 8 |
| VaultScraper.vb | 28 | 0 | 7 | 21 |
| VaultDownloadRules.vb | 46 | 0 | 15 | 31 |
| VaultDownloadRules.ProjectInfo.vb | 11 | 0 | 3 | 8 |
| UserResponseEditor.vb | 5 | 0 | 0 | 5 |
| UpdateInstaller.vb | 4 | 0 | 0 | 4 |
| TaskbarProgress.vb | 4 | 0 | 2 | 2 |
| SteamWorkshop.vb | 22 | 0 | 0 | 22 |
| SteamWorkshop.ModInfo.vb | 11 | 0 | 5 | 6 |
| SteamWorkshop.IdInfo.vb | 15 | 0 | 6 | 9 |
| SteamWorkshop.IdFileInfo.vb | 6 | 0 | 3 | 3 |
| StartScreenManager.vb | 82 | 0 | 0 | 82 |
| StartScreenInfo.vb | 42 | 0 | 0 | 42 |
| SlideShow.vb | 18 | 0 | 0 | 18 |
| Settings.vb | 27 | 0 | 0 | 27 |
| Settings.WebMenu.vb | 8 | 0 | 1 | 7 |
| Settings.RunMenu.vb | 8 | 0 | 0 | 8 |
| Settings.Profiles.vb | 15 | 0 | 0 | 15 |
| Settings.Preferences.vb | 10 | 0 | 0 | 10 |
| Settings.MenuCommon.vb | 13 | 0 | 0 | 13 |
| Settings.MapFolders.vb | 13 | 0 | 0 | 13 |
| Settings.MapFiles.vb | 10 | 0 | 0 | 10 |
| Settings.MapExtensions.vb | 15 | 0 | 0 | 15 |
| Settings.MapExcludes.vb | 15 | 0 | 0 | 15 |
| Settings.MapExceptions.vb | 9 | 0 | 0 | 9 |
| Settings.MapCommon.vb | 4 | 0 | 0 | 4 |

## Work queue — GAP? methods (no port match; investigate)

First 60 shown. A `GAP?` means the auto-matcher found no name/comment hit in the
port — it is a *candidate* miss to confirm, not a proven gap (the port may
implement it under a different name).

| VB ref | class | method | kind |
|---|---|---|---|

_(0 GAP? methods total; see ledger_members.csv for the full list.)_

## Findings (confirmed divergences)

These are real divergences confirmed against the VB source during audit design
(2026-07-15). They demonstrate the ledger catches behavior/layout/depth gaps that
the command-level audit did not.

1. **Empty groups not rendered for drag-drop** — `NIT.ModView.vb:69` `ApplyGroupsAndStatus` loops every `pd.Groups.Values` and calls `FvMods.AddGroup` for each, so empty groups still render (enabling drag-into-empty-group). The port's `FileView.populate` only emits groups that have members. → behavior gap.
2. **Ribbon tabs centered, not left-aligned** — `TbRibbon` is a WinForms `TabControl` (tabs left-packed); the port centers them. → designer-property gap.
3. **Settings depth (content gap, not just form)** — VB exposes 181 `My.Settings.*` keys; stripping Map/Colour/Path/Private internals leaves ~40-50 real user preferences (`Behaviour*`/`Config*`/`File*`), of which the port's settings model holds only ~10. Some map to ported features under other names, but genuinely-unmodelled ones include `ConfigMaxCrcThreads`, `ConfigPortraitDisplaySize`, `BehaviourSelectGameMod`, `ConfigDefaultGroup`, `ConfigSavesRetention`, `FilterSkillsByRank`. → run the Settings sub-sweep (enumerate every pref key, classify, build the missing ones).

