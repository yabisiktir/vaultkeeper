# Stage 3g — portraits and start screens

Method: NIT's `PortraitManager.vb` (`PopulatePortraits`, `IsPortraitFile`,
`RbApplyExcludes`, `ExcludePortrait`, `PopulateWizard`, `RbEditPortrait`,
`RbCreateInstaller`, `TsInvalidPortraitSizes`), `Defs.TgaToBitmap`,
`StartScreenInfo.vb` (`GetNextName`, `GetStandardAvailable`/`GetPrefixedAvailable`,
`ToggleActiveScreen`), `NIT.Common.AutoLoadscreen`/`InstallLoadscreen`,
`NIT.Workers.BgRunNwn`, `RbnPlay_MouseUp` and `StartScreenManager.RbDeleteFile`/
`RbRename` were compared line by line with the controller and both dialogs.

## Portraits

| ID | Area | Finding | Verdict |
|---|---|---|---|
| P1 ✅ | Apply Excludes | VK wrote the wizard excludes and then only re-marked the mod as an installer, so the payload was not rebuilt and the excluded portraits stayed in the installer and in the game. NIT runs Create Installer with installer-restore forced on. Now a real rebuild + reinstall (`rebuild_installer`). | BUG → fixed |
| P2 ✅ | Apply Excludes | VK searched only the mod's loose files for the portrait; portraits usually come inside an archive, where it found nothing ("not in this mod's installer sources"). NIT builds the list with archives extracted. | BUG → fixed |
| P3 ✅ | Create Installer button | Same marker-only rebuild as P1. | BUG → fixed |
| P4 ✅ | Override option | Outside `portraits`, NIT counts `…h.tga` only when the `m` and `t` sizes are installed too; VK listed any `…h.tga`, so textures ending in "h" appeared as portraits. | BUG → fixed |
| P5 ✅ | Order | NIT sorts by group, then mod, then file; VK by mod. | fixed |
| P6 ✅ | Edit Portrait | NIT opens the mod's source files in `_Downloads`, so the edit survives the next build; VK opened the installed game copies, which the next install overwrites. VK falls back to them when there is no single source (NIT then offers no edit). | BUG → fixed; fallback VK-better |
| P7 | Apply Excludes, NIT | NIT loops over *all* excludes for each mod and can add `Nothing` entries when a size is not found; VK adds only the mod's own, found files. | NIT artefact |
| P8 | Invalid sizes | Same rule (a size is invalid only if it is no portrait size at all). | same |
| P9 | `ConfigFlipPortraits` | Defined and described in NIT's settings but read by nothing; the flip in `TgaToBitmap` is unconditional. | NIT artefact (no setting needed) |
| P10 | Display | VK honours the TGA vertical-origin bit. NIT additionally flips right-origin files and crops portraits to the game's 16:25 visible area. Display only; for the screen-parity phase. | noted |
| P11 | `remove_installed_portrait` | An older, unused controller method that hard-deletes installed portraits without annealing. No UI calls it. | dead code, noted |

## Start screens

| ID | Area | Finding | Verdict |
|---|---|---|---|
| T1 ✅ | Auto-Start Screen Selection | The setting was stored and never acted on. NIT installs the next start screen each time the game closes: the one after the active screen in its set, wrapping round, keeping the active type. Ported (`next_loadscreen`, called on game exit). Default off in both. | MISSING → ported |
| T2 ✅ | Play right-click | Shift+right-click switches between Standard and Prefixed sets (when prefixes are defined); Ctrl+right-click shows the installed screen. Plain right-click (open the manager) was already there. | MISSING → ported |
| T3 ✅ | Delete | VK deleted images with `unlink`. NIT recycles them; Shift makes it permanent. | BUG → fixed |
| T4 ✅ | Delete, reselection | NIT refills each slot whose image is gone from that slot's own set (Standard: first not auto-excluded; Prefixed: first enabled-prefixed) and keeps the active type; with auto-select on it installs the new active screen. VK took the first image by name, even an excluded one, and could flip the type. | BUG → fixed |
| T5 ✅ | Rename | NIT's bug @1271 writes the display name into the active-*type* line when the installed image is renamed. VK replicated it **by default**, and the dialog used the default: the active name stayed on a file that no longer exists and rotation stopped. Only the corrected assignment remains. | BUG (replicated) → fixed |
| T6 | Available sets | Standard = all images not auto-excluded (prefixed images included unless excluded, which is what Repair Prefixed is for); Prefixed = enabled prefixes. Same. | same |
| T7 | Delete, NIT | NIT installs `SelectedImage` but records `ActiveScreen`, which can differ; VK installs and records the active screen. | NIT artefact |

Regression tests: `tests/test_portrait_parity.py` (P1–P4, P6 fail on the old code)
and `tests/test_start_screen_parity.py` (T1, T3–T5).
