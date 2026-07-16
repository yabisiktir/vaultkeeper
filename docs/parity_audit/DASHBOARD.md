# NIT → Vaultkeeper parity coverage ledger

Machine-generated denominator of the original VB app, auto-matched against the
Python port. Every row carries a status; the audit is complete when no row is
`GAP?` / `AUTO-PORTED` (i.e. every unit is verified or explicitly categorised).

Regenerate: `python extract_vb.py <vb> ./out && python build_ledger.py ./out <port> .`

## Coverage

| Layer | Total | Accounted | Machine queue (AUTO-PORTED + GAP?) |
|---|---|---|---|
| Methods/props | 3284 | 3284 (100%) | 0 |
| Event handlers | 885 | 885 (100%) | 0 |
| Designer controls | 1777 | 1777 (100%) | 0 |

### Methods/props — status breakdown
- `Divergence`: 1332
- `Ported`: 1169
- `Deferred`: 415
- `N/A`: 188
- `Partial`: 180

### Event handlers — status breakdown
- `Divergence`: 554
- `Ported`: 148
- `Deferred`: 138
- `Partial`: 45

### Designer controls — status breakdown
- `Ported`: 1028
- `Divergence`: 371
- `Deferred`: 276
- `N/A`: 102

## Where to look — GAP? density by VB file (methods)

Files with the most unmatched methods surface first; these are the sweep priorities.

| VB file | methods | GAP? | AUTO-PORTED | accounted |
|---|---|---|---|---|
| WorkshopViewer.vb | 9 | 0 | 0 | 9 |
| WorkshopNameEditor.vb | 11 | 0 | 0 | 11 |
| WizardInfo.vb | 26 | 0 | 0 | 26 |
| WizardBuilder.vb | 34 | 0 | 0 | 34 |
| VaultScraperInfo.vb | 19 | 0 | 0 | 19 |
| VaultScraper.vb | 28 | 0 | 0 | 28 |
| VaultDownloadRules.vb | 46 | 0 | 0 | 46 |
| VaultDownloadRules.ProjectInfo.vb | 11 | 0 | 0 | 11 |
| UserResponseEditor.vb | 5 | 0 | 0 | 5 |
| UpdateInstaller.vb | 4 | 0 | 0 | 4 |
| TaskbarProgress.vb | 4 | 0 | 0 | 4 |
| SteamWorkshop.vb | 22 | 0 | 0 | 22 |
| SteamWorkshop.ModInfo.vb | 11 | 0 | 0 | 11 |
| SteamWorkshop.IdInfo.vb | 15 | 0 | 0 | 15 |
| SteamWorkshop.IdFileInfo.vb | 6 | 0 | 0 | 6 |
| StartScreenManager.vb | 82 | 0 | 0 | 82 |
| StartScreenInfo.vb | 42 | 0 | 0 | 42 |
| SlideShow.vb | 18 | 0 | 0 | 18 |
| Settings.vb | 27 | 0 | 0 | 27 |
| Settings.WebMenu.vb | 8 | 0 | 0 | 8 |
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

## Findings (all FIXED 2026-07-15)

The three findings that motivated the audit — behavior/layout/depth gaps the
command-level audit did not catch — are all fixed:

1. **Empty groups not rendered for drag-drop** ✅ FIXED — `controller.groups()` now seeds every visible group (incl. empty), matching VB `ApplyGroupsAndStatus`.
2. **Ribbon tabs centered, not left-aligned** ✅ FIXED — the ribbon left-aligns its tab row (`setExpanding(False)` + stylesheet).
3. **Settings depth (content gap)** ✅ DIAGNOSED + BUILT — VB exposes 81 real prefs vs ~10 modelled; classified (12 ported / 16 divergence / 10 perf / 33 deferred-features / 10 real add-a-setting gaps); all 10 now built + wired (see FINDING_3_SETTINGS.md).
Plus 2 MISSING methods fixed (Copy Details / Copy Level in Character Explorer), a Mod Explorer filter bar, a Mod Play Viewer end-level filter, and Portrait Prev/Next.

## Audit status — COMPLETE + VERIFIED

**All three layers 100% classified AND verified — 0 GAP?, 0 AUTO-PORTED, 0 MISSING.** The name-matched rows were verified in a dedicated pass: distinctive-name matches confirmed genuine (grep), and each VB file's AUTO-PORTED rows resolved at file granularity via `verify_files.json` (ported module → Ported; deferred/divergent subsystems reclassified). Every VB method / handler / control now carries an explicit, evidence-backed status. The only remaining work is optional: build more of the tracked Deferred features.

