# Next session — visual + help parity verification (the planned final phase)

Paste-ready handoff for a fresh chat. Continues the VB.NET → Python migration of the
"NWN Installer Tool" (port = **Vaultkeeper**).

> Subagents are allowed; the main agent may use cheaper models for the mechanical work.

## Status — the deferred-feature queue is COMPLETE

The previous queue (items 1–8: Finding-3 settings, Run Menu, Installation Manager,
Hak-patch + Alias editors, Original-restorers, Start-screen prefix editor, Copy-MapId +
DailyPlayTime) is **done and merged to `main`** (commits `9466d7c..ee1cea2`). Every
previously-dead command is now wired. The parity ledger is clean:

- **0 GAP? / 0 AUTO-PORTED** across all three layers (methods / handlers / controls).
- Method layer: **1198 Ported / 182 Partial / 378 Deferred / 1338 Divergence / 188 N/A**.

The functional 1:1 feature port is effectively complete. What remains is **not** a set of
forgotten features — it is (1) deliberate cross-platform **divergences**, (2) **data-blocked**
network features, (3) **low-value** platform items, and (4) **Partial** ports that could be
deepened. See "What's genuinely left" below.

## First, get context

Read these memory files: `nit-vaultkeeper-handoff`, `nit-parity-audit`,
`nit-help-and-parity-plan`, `nit-installed-original-tool`. Then read
`docs/parity_audit/README.md` and `DASHBOARD.md`.

## GOAL this session — VISUAL + HELP PARITY VERIFICATION

Now that features are ported, **prove the port looks and behaves like the original** —
something feature-porting alone cannot show. This is the owner's planned final phase
(`nit-help-and-parity-plan`).

1. **Drive the real original** in the CrossOver bottle (`nit-installed-original-tool` has
   the runnable `.exe` + the user-facing CHM = ground truth: 236 HTML topics + 729
   screenshots, directly readable in the CrossOver install). Capture live screenshots of
   each screen/dialog.
2. **Render the corresponding Vaultkeeper screens** offscreen
   (`QT_QPA_PLATFORM=offscreen`) and compare against the original + the CHM screenshots.
   Log concrete visual divergences (layout, labels, control set, ordering, defaults) using
   the same "finding" discipline that produced the three parity-audit findings.
3. **Fix the high-value divergences** faithfully; **defer-with-note** anything that is an
   intentional cross-platform divergence. Confirm a per-dialog **Help** button exists on
   every dialog (the help viewer + CHM are already bundled — `ui/dialogs/help_viewer.py`).

### Alternative tracks (state which you pick)
- **(b) Deepen the 182 `Partial` ports** by value (each is noted in code + `seeds.json`).
- **(c) The large true-LazWorks-FileView rewrite** (Contents/Details drag-drop, copy-paste,
  rich-text, columns/sorting). **This pane divergence is intentional** — confirm the owner
  wants pixel parity before starting; it is a big rewrite, not a bug.

## What's genuinely left (all accounted for — none are unintended gaps)

- **Intentional divergences:** true LazWorks FileView panes; Windows taskbar / crash-dumps /
  auto-update / debug-options menu (cross-platform, left disabled).
- **Data-blocked:** Steam Workshop **network title fetch** (needs a live Steam Community request).
- **Low-value:** start-screen **slideshow** timer; shared-store / BackupManager network **sync**
  (no NRBF writer / shared store, per the DATA STRATEGY decision).
- **Bounded tails** of ported features (each noted): InstallationManager group-add/remove +
  sort-by-date; Alias CustomAliasFile state machine + game-saves shared/per-profile toggle +
  reset-to-standard; original-restorer campaign nuances + PruneAutoConfig + auto-run-on-load;
  DailyPlayTime day-conversion consumer (no estimate consumer in the port yet).

## Where things are

- **Port (edit here):** `NWN Installer Tool/vaultkeeper/src/vaultkeeper` — own git repo, on `main`.
- **VB ground truth:** `NWN Installer Tool/NWN Installer Tool` — the ORIGINAL app.
- **Runnable original + CHM:** in the CrossOver bottle (see `nit-installed-original-tool`).
- **Audit ledger:** `NWN Installer Tool/vaultkeeper/docs/parity_audit/`.
- Dev uses `./.venv/bin/python` (py3.13). Tests: `QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m pytest`.
- Suite is green **except 2 pre-existing real-data golden failures**
  (`test_ee_resolution_lights_up_real_installed_mods`, `test_real_import_open_shows_installed_grouped`)
  — they fail on pristine code too (live NIT Store drift: 23 mods vs the 21 golden). Ignore them;
  do NOT "fix" by editing asserts.

## How to work

- Ground every behaviour/default/layout in the VB source or the CHM before changing the port.
- Keep ruff clean (src+tests), add tests, and **validate with the ledger after each change**:
  ```
  cd docs/parity_audit
  python extract_vb.py "<vb src>" ./out && python build_ledger.py ./out "<port src>" .
  ```
  Confirm `DASHBOARD.md` still shows **0 GAP? / 0 AUTO-PORTED**.
- Commit per tested increment (end the message with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`). Ask before pushing. Branch
  first if on `main`.

## Start

Say which track you're taking (visual/help parity verification is the recommended default).
For the verification track: pick a handful of screens, screenshot the original + render the
port, list divergences, fix the high-value ones, and continue screen-by-screen.
