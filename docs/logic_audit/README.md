# Logic audit: NIT vs Vaultkeeper (differential)

The parity ledger (`../parity_audit/`) proves every VB symbol is *accounted for*.
It never proves the port *computes the same answer*: 1,345 methods are "Divergence"
under ~20 shared notes, and 525 "Ported" rows had no name match at all. This audit
runs the **original NIT code** and **Vaultkeeper** on identical inputs and diffs
the outputs.

## How the original runs

`NWN Installer Tool.exe` (v8.0, .NET 4.8) is loaded as a library by a small C#
harness (`harness/`) that runs inside the CrossOver bottle **NIT**, where real
.NET WinForms is available (Mono cannot build NIT's main form, which `Defs`'s
static constructor touches). The harness replays the non-UI part of NIT's
start-up against a **sandbox** and then answers queries from stdin as JSON lines.

Safety rules:
- .NET keys `My.Settings` by the *entry* program, so the harness has its own
  settings folder (factory defaults) and never reads/writes NIT's `user.config`.
- The bottle's `Documents` is a symlink to the owner's real `~/Documents` (real
  NWN folder, 26 GB). The harness is only ever pointed at `C:\nitdiff\...`.
- Disk budget (~13 GB free): archives are **listed, never extracted**; scenario
  fixtures are tiny placeholder files; the sandbox is deleted after every run.

## Comparing across CrossOver and native

Absolute paths differ (`C:\nitdiff\...` vs `/private/tmp/...`; `nwn.ini` aliases
are platform-specific). Every comparison is made on **normalised** outputs:
paths relative to the sandbox root, `\` → `/`, and folders expressed as NWN
folder *names* (`hak`, `override`, …), never absolute locations. Case is compared
as each app would treat it on Windows (case-insensitive) unless the finding is
itself about case.

## Stages

Each stage has a fixed scope, an exit criterion, and one output file. A stage is
not "done" until its findings are triaged.

| # | Stage | Scope | Exit criterion | Output |
|---|---|---|---|---|
| 0 ✅ | **Harness bootstrap** | Headless NIT in the bottle; sandbox store + fake NWN user folder; default profile created by NIT's own code; JSON query loop; path normaliser | NIT answers a Mapper query and a Profile query; sandbox teardown verified | `stage0_bootstrap.md` |
| 1 ✅ | **Install core: function diffs** | File mapping (target folder, excludes, exceptions, prefixes, moves, ERF/demo checks), mod-name/version parsing, Vault download rules + prerequisites, dependency and conflict detection, change tracking | Every function pair run on the full corpus; every mismatch listed with input + both outputs | `stage1_findings.md` |
| 2 ✅ | **Install core: scenario diffs** | Same scripted sequences in both apps on identical sandboxes: install, install-with-conflict, reinstall, uninstall (incl. dependants), move/rename, profile switch. Diff files on disk + persisted records after each step | All scripts run; every divergence in resulting state listed | `stage2_findings.md` |
| 3 ▶ | **Beyond install: other features** (separate phase; plan below) | Game Saves Manager + backups/restore, play-data/client-log, character/BIC reading, portraits + start screens, installer/wizard creation, Workshop, DocOrganiser, INI/alias handling, settings import/export, validation/recovery tools | Same method as 1-2, feature by feature, each with its own corpus | `stage3_<feature>.md` |
| 4 | **Residual code review** | Ledger rows no stage could execute (UI-coupled logic), core files first | Every residual row has a verdict backed by a VB-vs-Python branch comparison, not a note | `stage4_review.md` |
| 5 | **Triage + fix** | Each finding: bug / deliberate improvement / platform difference; fix bugs with a regression test that encodes NIT's answer | No untriaged findings | `FINDINGS.md` |

Stages 0–2 are done (2026-09-27; findings ranked in `FINDINGS.md`), and their
findings are triaged and fixed (stage 5 batches 1–10).

## Stage 3 plan (sub-stages)

Ordered by risk: what every user hits first, then what can lose data, then the
rest. Each sub-stage runs NIT's own code on a sandbox (harness scenario or
query) and Vaultkeeper on the same input, diffs the normalised result, and ends
with every difference triaged (BUG / DELIBERATE / VK-better / NIT artefact).
Where NIT's behaviour is UI-only and cannot run headless, the VB branch is
compared by reading, and the finding says so.

| # | Sub-stage | Scope | Method | Exit criterion |
|---|---|---|---|---|
| 3a ✅ | **First run, profiles, INI** | the first-run questions and what each answer changes; `nwn.ini` alias writes (S4); `userpatch.ini` creation; the initial restorers ("NWN INI Files Restorer"); profile create / switch / rename / delete | harness: fresh store → first run → snapshot of store + user folder; switch-profile scenario. VK: `first_run.py` with the same answers | first-run end state identical or triaged |
| 3b ✅ | **Settings: defaults and meaning** | every NIT `My.Settings` value vs the VK setting it maps to: default value, and what code reads it (U2 and `move_added_mods` were both this kind) | parse `Settings.settings` + `Settings.Config.vb` descriptions; map to `config/settings.py`; read each consumer | every NIT setting mapped, defaulted and consumed as NIT does, or triaged |
| 3c ✅ | **Backups and recovery** | store backup / restore, Rebuild Database, Validate Profile Data, Recover Group, Check Installed Files, Recognise Installed | harness scenarios that damage a store (missing files, stale records, orphan groups) then run each tool | resulting store identical or triaged; no path loses data |
| 3d ✅ | **Game saves** | Game Saves Manager: save → mod mapping (`GameSaveNameMap`), backup / restore / delete / move of saves | harness queries on real save names + scenario on fixture saves | mapping identical on the corpus; scenario end state identical |
| 3e | **Play data and logs** | play-time records, client/engine log parsing, played-module detection | feed the same log files to both | parsed records identical |
| 3f | **Installer tooling** | Wizard Builder validate/save, Publish, Change Installer, Update Installer (installer paste) | scenarios on fixture mods | resulting files identical |
| 3g | **Portraits and start screens** | Portrait Manager, load screens, `po_*` handling | fixture portraits | resulting files identical |
| 3h | **Steam Workshop** | Workshop import, ID map (`WorkshopIdMap`), subscription handling | fixture Workshop folder | imported mods identical |
| 3i | **Documents** | DocOrganiser, related files, notes | fixture mod folders | resulting layout identical |
| 3j | **Characters** | BIC reading (VK's is far richer; check only NIT's fields) | real `.bic` corpus | NIT's fields identical |

Each writes `stage3<letter>_<feature>.md`; findings join `FINDINGS.md`. Stages 1-2 were the pilot; stage 3 is scheduled only after 1-2's findings are
triaged, so the method is calibrated first.

## Corpus (stage 1)

- File listings of the owner's mod archives (`7z l -slt`, no extraction).
- NIT's bundled `DownloadRulesV3.txt` / `Application Definitions.txt`.
- Synthetic edge cases generated per function (case, missing extension, nested
  folders, prefix/suffix matches, reserved names).
