# Stage 0 — harness bootstrap (DONE 2026-09-27)

Exit criterion met: NIT v8.0.0.80 (source tree `bin/Debug`, with PDBs) starts
headless in the CrossOver bottle against the sandbox and answers Mapper queries;
the sandbox is removed after each run.

## How it runs

`harness/run_nit.sh` compiles `NitHarness.cs` with Mono's `mcs`, copies it next to
a slim copy of the v8.0 build in `C:\nitdiff\nit80` (15 MB: no ffmpeg,
chromedriver, CHM), and runs it with CrossOver's `wine --bottle NIT`.
`harness/make_sandbox.sh` builds the sandbox (4 KB before start-up, 192 KB after).

The harness replays the real start-up rather than re-implementing it:
1. presets `My.Settings` (sandbox store/user/library/temp, not-first-run);
2. **guard**: NIT's own `Paths.ValidateExtendedUser/Lib` must accept the sandbox,
   otherwise NIT would fall back to `Documents\Neverwinter Nights`, which in the
   bottle is a symlink to the owner's real 26 GB folder → abort;
3. `Defs` static constructor (it creates the NIT form), then the
   `MyApplication_Startup` splash replay, then `Application.Run(form)` so
   `NIT_Load` and `NIT_Shown` run exactly once, as in the real app;
4. a `Shown` handler added after NIT's own re-checks that `Paths.Tool` and
   `Paths.ExtendedUserPath` are inside the sandbox, runs `C:\nitdiff\in.tsv`,
   writes `out.tsv`, exits.

Every modal dialog is answered from `harness/dialog_rules.tsv` and logged; a
dialog with no rule aborts the run (never click blindly).

## Things the harness must work around (not NIT findings)

| Symptom | Cause | Workaround |
|---|---|---|
| Mono can't create the NIT form | Mono WinForms lacks LazWorks controls | run in the bottle's real .NET 4.8 |
| DragDrop registration failed | harness thread was MTA | `[STAThread]` |
| WordPad lookup throws in the form ctor | `GetFolderPath(ProgramFiles)` is empty under Wine | preset `WordPadPathValue = ""` |
| "Invalid command line parameters" | NIT parses the process command line | watchdog via `NITDIFF_WATCHDOG` env var |
| `NwnFolderInfo` duplicate key | fake nwn.ini had aliases a real EE one lacks | alias set copied from a real EE nwn.ini |
| First-run answers leaked between runs | NIT saves `My.Settings`; the harness's own `user.config` persisted | `run_nit.sh` deletes `AppData\Local\NitHarness` every run |

## First-run prompts NIT raised in a fresh store (answers used)

1. Create the missing Profiles sub-folder? → Yes
2. Alias Section of nwn.ini changed (adds `NWMFiles=<lib>\data\nwm`, `SOURCEOVERRIDE=<user>\latest-resource-override`) → OK
3. Mod Player or Builder? → Player / Builder (stage 1 runs both)
4. Group Set for EE Mods → the recommended first option
5. Create Restorers for files installed by NWN? → Yes
6. Apply Theme colours to RTF Notes? → No

Item 2 is a behaviour to compare in stage 3 (INI handling): NIT **writes two
aliases into nwn.ini**. A fresh NIT store also contains the "NWN INI Files (Auto)"
and "2. NWN INI Files Restorer" mods; compare with Vaultkeeper's first run.

## Version note

The installed NIT in the bottle is **v7.4.1.19**; the port was made from the
**v8.0.0.80** source. All comparisons use the v8.0 build.
