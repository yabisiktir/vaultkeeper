# Next session — continue porting Deferred features (keep proving no gap)

Paste-ready handoff for a fresh chat. Continues the VB.NET → Python migration of the
"NWN Installer Tool" (port = **Vaultkeeper**). **Goal: port the remaining Deferred/Partial
features and keep proving NO functionality gap exists.**

> Subagents are allowed; the main agent may use cheaper models for the mechanical work.

## First, get context

Read these memory files (full history/decisions):
`nit-parity-audit`, `nit-vaultkeeper-handoff`, `nit-migration-project`, `nit-installed-original-tool`.
Then read `docs/parity_audit/README.md` and `DASHBOARD.md`.

## Where things are

- **Port (edit here):** `NWN Installer Tool/vaultkeeper/src/vaultkeeper` — own git repo, on `main`.
- **VB ground truth:** `NWN Installer Tool/NWN Installer Tool` — 203 `.vb` files, the ORIGINAL app.
- **Audit ledger:** `NWN Installer Tool/vaultkeeper/docs/parity_audit/`.
- Dev uses `./.venv/bin/python` (py3.13). Tests: `QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m pytest`.
- Suite is green **except 2 pre-existing real-data golden failures**
  (`test_ee_resolution_lights_up_real_installed_mods`, `test_real_import_open_shows_installed_grouped`)
  — they fail on pristine code too (live NIT Store drift). Ignore them; do NOT "fix" by editing asserts.

## State

The parity audit is **COMPLETE + VERIFIED** — every VB method (3284), handler (885) and control
(1777) has an explicit status: Ported / Partial / Deferred / Divergence / N/A. **0 GAP?, 0 unverified,
0 MISSING.** So the work now is to turn **Deferred/Partial → Ported**.

## Work queue — the port's genuine feature gaps (Deferred), roughly by value

Port each **faithfully** from the VB source; if a piece can't be done faithfully, **defer it with a
note** rather than invent behaviour. These are real features — NOT the intentional cross-platform
Divergences (Windows taskbar / crash-dumps / auto-update — leave those).

1. **Finding-3 settings still unbuilt** (small, high-value): `confirm_saves`, `delete_leto_logs`
   (VB `ConfigDeleteLetoLogs` — auto-runs `remove_leto_log_files`; find the VB trigger point),
   `portrait_display_size`. Pattern already established: `config/settings.py` field +
   `ui/dialogs/settings_dialog.py` Behaviour tab + a real hook + a test. See `FINDING_3_SETTINGS.md`.
2. **Run Menu** (external launch programs) — VB `Settings.RunMenu` + `SetRunMenu`. The port has a
   Web Menu; Run Menu is entirely absent.
3. **Installation-sets editor** (`MsInstallationManager`) — VB `InstallationManager*.vb`
   (checkpoints / user-defined mod sets). The install ENGINE is ported; the sets UI isn't.
4. **Alias section editor** (`MsAliasSection` — nwn.ini `[Alias]`) + **Hak-patch editor**
   (`MsHakPatchEditor`). Read-only models exist; editors deferred. Respect config-isolation
   (never write game files without a confirm prompt).
5. **Original-restorers** (`MsCreateOriginalRestorers` / `AutoOriginalRestorer` subsystem in
   `NIT.ModView.vb` + `ProfileData.vb`: `UseNwOriginal`/`UseEeOriginal`/`BuildOriginalFiles`/
   `ValidateOriginals`).
6. **Start-screen**: slideshow + prefix editor (`MsEditStartScreenPrefixes`).
7. **True LazWorks FileView** (contents/details drag-drop, copy-paste, rich-text) — large; the port
   renders these panes structurally differently on purpose. Confirm scope before starting.
8. **Steam Workshop** network title fetch + Copy-MapId-Rule; **DailyPlayTimeInfo** auto day factor.

## How to work each item (faithful-or-defer)

- Read the VB source for the feature FIRST (exact methods are in the ledger CSVs). Ground every
  behaviour + default in the VB; verify data-contract values against the source before coding.
- Implement headless/domain logic first (testable), then thin Qt UI. Match the port's patterns:
  a `controller` method returning testable data + a `ui/dialogs/*.py` dialog + wire a command id.
- Add tests. Keep ruff clean. Commit per tested increment (end the message with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`). Ask before pushing.
- **VALIDATE with the ledger after each feature:** move the ported methods Deferred→Ported by
  editing `verify_files.json` (file granularity) or `seeds.json` (name), then regenerate:
  ```
  cd docs/parity_audit
  python extract_vb.py "<vb src>" ./out && python build_ledger.py ./out "<port src>" .
  ```
  Confirm `DASHBOARD.md` still shows **0 GAP? / 0 unverified** and the feature's rows are now Ported.
  **Never mark Ported on a name match alone — confirm the port behaviour actually exists.**

## Subagents (use cheaper models for the mechanical work; verify their output)

- Use **haiku** subagents for READ-ONLY research/classification (e.g. "read VB file X's methods and
  describe what each does + where a faithful port would live"). They gather EVIDENCE reliably but are
  UNRELIABLE on the final Ported-vs-Deferred-vs-Divergence call — the **main agent must adjudicate**.
- Do all hot-file edits (`controller.py` / `main_window.py` / `settings*.py`) yourself, SERIALLY.
  Fan out only conflict-free NEW files to subagents; apply their proposed hot-file edits yourself.
- Spot-check every subagent claim against the VB + port before trusting it.

## Start

Regenerate the ledger, read the Deferred rows, pick item 1, port + test + validate it, commit, and
continue down the queue. Say which item you're on.
