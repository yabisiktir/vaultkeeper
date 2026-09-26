# Stage 2 — install core: scenario diffs

Both apps run the same scripted scenario on identical sandboxes (fixtures from
`stage2/make_fixtures.py`: every file's content names its owner, so a snapshot
shows which copy won). A normalised snapshot is taken after every step:
game-folder files + content, EE-library files, the profile's mod folders
(installer layout), and each mod's installed flag / state / dependencies.

- NIT: `stage2/run_nit_scenario.sh` → harness `scenario` command. Operations call
  the same form methods the menu clicks call: `ModPaste`, `PerformCreateInstaller`,
  `InstallMods`, `UninstallMods(list, dependencies:=True)`,
  `ActivatedEventProcessing` (rescan). NIT settles 3 s between steps (idle app).
- VK: `stage2/run_vk_scenario.py`, sandboxed like the test suite (HOME/XDG/APPDATA,
  `app_paths._home`, `send2trash` → sandbox bin), first run through
  `auto_configure_first_run` + `answer_player_excludes`; operations mirror the
  UI handlers (`paste_mod_sources`, `_on_create_installer`'s
  `build_installer_payload` sequence, `set_mod_dependencies`, `install`,
  `uninstall`, `rescan_installed_state`).
- Compare: `stage2/compare.py <dir>`.

## Scenario "basic" (`stage2/scenario_basic.tsv`) — DONE

paste 3 mods → create installers → Gamma depends on Alpha → install Alpha, Beta
(conflict on `override/shared.2da`, over a pre-existing user file), Gamma →
uninstall Alpha → delete/edit installed files outside the app → rescan →
uninstall Beta, Gamma.

**Game folder: identical at every one of the 13 snapshots** (which copy wins a
conflict, anneal back to Beta's copy on Alpha's uninstall, outside edits, final
cleanup). The core install/uninstall/conflict logic is faithful.

| # | Finding | Triage |
|---|---|---|
| S1 | **Patch INI written to the wrong file/folder on EE.** NIT (EE) maintains `userpatch.ini` in the *user* folder and leaves `nwnpatch.ini` alone (`NwnFolderInfo`: EE → `UserPatchIniFile`). VK always writes `<game_root>/nwnpatch.ini` (+ `.bak`) — the **game installation folder** (`controller.py` `ctx.game_root / "nwnpatch.ini"`). Effect: patch-haks registered by VK are not in the file EE reads for user patches, and VK modifies the install folder. | **BUG (high)** — prove with a patch-hak scenario |
| S2 | **NIT-managed "(Auto)" restorers missing.** On every activation/after installs NIT maintains auto-backup mods of the database files, INI files, character journals and NIT config (`RunAutoRestorers`: `AutoDatabaseRestorer`, `AutoIniFileRestorer`, `AutoJournalFileRestorer`, `AutoNitConfigFileRestorer`) in group "ZZZ. NIT Managed Restorers (Auto)". A fresh NIT store already has "NWN INI Files (Auto)" and "2. NWN INI Files Restorer". VK has only the character auto-restorer. | **BUG** (missing feature, silent data-safety loss) |
| S3 | **Mod state after uninstall is wrong in VK.** After uninstalling Alpha (whose `shared.2da` is now Beta's copy in the game), NIT shows Alpha *Not Installed*; VK shows *Some Installed and Match* — but the file in the game is Beta's (different content and size). Also while installed-and-overridden NIT shows *Installed and Overridden*, VK *Match Override*; and for a not-installed mod sharing a file, NIT *Some and Overridden* vs VK *Some and Match*. The state drives the mod-list icon the user sees. | **BUG** (display logic; inspect `ModData.set_mod_state`) |
| S4 | NIT writes two aliases into `nwn.ini` on first run (`NWMFiles`, `SOURCEOVERRIDE`); VK leaves `nwn.ini` untouched. | **VERIFY** in stage 3 (INI handling): what the aliases are for |
| S5 | **Both apps destroy a pre-existing user file.** `override/shared.2da` that no mod installed (content "ORIGINAL") is overwritten by the first install and deleted at the final uninstall; neither app backed it up or restored it. | Same in both — not a regression; worth a VK improvement later |
| S6 | NIT-side defect found by the harness: **LazWorks `FileOperations` queue race.** A worker that just found the queue empty is still `IsBusy` when the UI thread queues the next item, so `RunOperationWorkers` skips it and the item is never processed — the log says "Items Deleted: N" and then "Delete failure" with no reason; files stay behind. Hit on 5/5 unpatched runs under Wine (timing-dependent; plausible but unproven on Windows). The harness patches it (restart workers if items remain; logged, fired 6× in one run) so comparisons use NIT's intended outcome. | NIT bug — VK better (no such race) |

Harness mistakes caught on the way (not findings): calling VK's
`create_installer` (writes only the identifier) instead of the UI's
`build_installer_payload` sequence; enum spelling differences
(`SomeAndOverridden` vs `SOME_AND_OVERRIDDEN`) normalised in `compare.py`.

## Scenario "deps" (`stage2/scenario_deps.tsv`) — DONE

A patch-hak mod (`patch/delta_patch.hak`) and a dependency chain (Zeta → Epsilon):
install/uninstall in both orders.

- **S1 proven:** after installing Delta Patch, NIT lists `delta_patch` in
  `<user>/userpatch.ini`; VK lists it in `<game install>/nwnpatch.ini`. Every
  other step identical.
- **Dependencies: identical.** Installing Zeta installs Epsilon first in both;
  uninstalling Zeta and Epsilon leaves the same files; mod states match at all 11
  snapshots.

## Scenario "archives" (`stage2/scenario_archives.tsv`) — DONE

Paste three generated archives (raw-named `.7z` with `hak/`+`override/`+docs; a
`.zip` whose content sits under one top folder; a `.zip` holding a nested `.7z`),
build installers, install, uninstall. Scenario lines use `@stem` = "the mod each
app created from that source" (names differ by N1; `compare.py` normalises them).

Extraction layout, single-top-folder handling, the nested archive, installers
and **every game file: identical**.

| # | Finding | Triage |
|---|---|---|
| A1 | **The pasted archive is not kept.** NIT copies the source archive into the new mod's `_Downloads` folder (`ModPaste` → `SetModPasteTarget`); VK extracts it and keeps nothing. Once the user deletes their download, VK's store has no original to rebuild from (NIT's "rebuild from download", related-files view and Open Downloads all rely on it). | **BUG** |

## Scenario "update" (`stage2/scenario_update.tsv`) — DONE

Install Alpha + Beta **in one operation**, then change Alpha's source while it is
installed (new version of `alpha.hak`, a new `alpha_new.hak`, `music/mus_alpha.bmu`
deleted), rescan, rebuild Alpha's installer, install again, uninstall both.

| # | Finding | Triage |
|---|---|---|
| U1 | **Conflict winner depends on batch order.** Installing Alpha and Beta together leaves NIT with Beta's `override/shared.2da` (NIT resolves by mod priority — `FileKeyInfo.Comparer`, later wins, the same result as installing them one by one); VK leaves **Alpha's**. Installed separately (scenario basic) both agree, so VK's winner follows batch order rather than priority. Silent: the game runs different content. | **BUG (high)** |
| U2 | **Rebuilding an installed mod leaves it half-installed.** NIT's default `BehaviourInstallerRestore = True` reinstalls a rebuilt mod that was installed, so the game gets the new version at once. VK's `installer_restore` defaults to **False**: after the rebuild the mod shows not-installed while the game still holds the old files, until the user installs again. | **BUG** (default mismatch) |
| U3 | **Stale files survive a rebuild.** A file deleted from the mod's source (`music/mus_alpha.bmu`) stays in VK's rebuilt installer and therefore stays in the game even after reinstalling. NIT's rebuilt installer drops it and the reinstall removes it from the game. | **BUG** |
| U4 | State naming as in S3 (NIT *Installed* vs VK *Match Override* for the overridden mod). | see S3 |

## Scenario "restorer" (`stage2/scenario_restorer.tsv`) — DONE

A pre-existing user file (`override/shared.2da`, owned by no mod) → Create
Restorer → install a mod that overwrites it → uninstall that mod. NIT runs the
real `MsCreateRestorer_Click` (the harness types the name into the dialog); VK
runs what `MainWindow._on_create_restorer` does with no mod selected.

| # | Finding | Triage |
|---|---|---|
| R1 | **Create Restorer means different things.** NIT collects every installed file no mod owns (`pd.UnknownSourceFiles` — here `shared.2da` and the library's `Chapter1.nwm`) into a new restorer mod the user names; the restorer is "installed", so when a mod that overwrote the file is uninstalled, NIT's anneal **puts the original back**. VK's Create Restorer only tags the *selected* mod as a restorer (`create_restorer` writes a `.nitres`); only the character variant collects unowned files. End result: NIT's final game has `ORIGINAL::shared.2da`; **VK has lost the file**. This is the protection that S5 lacked. | **BUG (high, data loss)** |

## Status

Stage 2 scenarios run: basic, deps, archives, update, restorer. The profile
switch moves to stage 3 (profile management), where creating and switching
profiles is exercised as a feature rather than as an install step.
