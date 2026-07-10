# Visual / experience parity report (Stage 2, Phase B)

Verifies that Vaultkeeper's ported screens look and behave like the original
VB.NET **NWN Installer Tool**. Ground truth = the screenshots inside the original's
help CHM, now bundled under `src/vaultkeeper/ui/resources/help/lib/` (each dialog's
help topic embeds its screenshot).

**Pass/fail bar = structural / experiential parity, NOT pixel parity.** Qt-on-macOS
and WinForms-on-Windows never pixel-match (native widgets, fonts, chrome, DPI differ).
"Parity" means the same controls, captions, order, grouping, panes and workflow.

## How to reproduce (repeatable)

1. Render the port dialog offscreen:
   ```
   QT_QPA_PLATFORM=offscreen ./.venv/bin/python -c "<build dialog>; dlg.grab().save('out.png')"
   ```
   (see `tests/test_*_viewer.py` / `tests/test_*_manager.py` for the build setup of
   each dialog.)
2. Find the reference screenshot: open the dialog's help topic
   (`<ControlName>.htm`, e.g. `bhgamemanager.htm`) and read its `lib/*.png` `src`.
3. Compare structurally (controls, order, captions, icons, panes, workflow).
4. Record the result below as **Verified**, **Differing** (should be fixed to match)
   or **Divergent** (intentional cross-platform / bounded-port difference).

## Status legend

- ✅ **Verified** — structurally matches the original.
- 🟡 **Differing** — real differences that should be reconciled toward the original.
- 🔷 **Divergent (intended)** — difference is a deliberate bounded-port or
  cross-platform / config-isolation choice, recorded as expected.
- ⬜ **Pending** — not yet compared this pass.

## Findings

### Character Explorer — ✅ Verified (with minor divergences)

Reference: `mscharacterviewer.htm` → `lib/NewItem 315.png`.

| Element | Original | Port | Verdict |
|---|---|---|---|
| Character list (left) | ✓ | ✓ | ✅ |
| Portrait | centre column | above the tabs | 🟡 position |
| Right pane tabs **Summary / Skills / Feats** | ✓ | ✓ (added this stage) | ✅ |
| Summary fields (race/class/alignment, XP, HP, Gold, ability scores, portrait, updated) | ✓ | ✓ | ✅ |
| List label | `.bic` filenames | character display name + level | 🟡 |
| Bottom bar: Search Names, Show all Levels, Select, Close | ✓ | — | 🟡 missing |

The key structure — the three-pane list / portrait / **Summary·Skills·Feats tabs** —
now matches the original. Remaining gaps: portrait column position, the search /
"Show all Levels" / Select bottom bar, and showing the `.bic` filename in the list.

### Mod Documentation Organiser — 🟡 Differing / 🔷 partly Divergent

Reference: `bhdocmanager.htm` → `lib/NewItem1341.png`.

| Element | Original | Port | Verdict |
|---|---|---|---|
| Heading text | ✓ | ✓ | ✅ |
| Downloads list + Contents list | stacked left | side-by-side | 🟡 arrangement |
| Document preview pane | one per list (2) | one shared, below | 🟡 |
| Version / Rename / Rename to / Uncheck All | toolbar + context menu | bottom buttons | 🟡 affordance |
| Rename / Rename To | ✓ | ✓ (this stage) | ✅ |
| Properties, Reset | ✓ | — | 🔷 deferred |
| Multi-mod queue ("1 of 3" in title) | ✓ | — | 🔷 deferred |

All the core content (both lists, preview, copy, rename/rename-to, version toggle,
uncheck-all) is present; the layout arrangement and the Properties/Reset/queue
extras differ.

### Game Saves Manager — 🟡 Differing / 🔷 Divergent (bounded port)

Reference: `bhgamemanager.htm` → `lib/NewItem1502.png`.

The port implements only the **archive / reduce / restore** slice (this stage). The
original is a full backup **manager** with a different layout:

| Element | Original | Port | Verdict |
|---|---|---|---|
| Reduce (keep-count) + Restore | ✓ | ✓ | ✅ |
| Save list | mods grouped, left; current game's save folders as a 2nd list ("regions") | one flat table (Folder/Save/Location/Type/Size) | 🟡 layout |
| Action toolbar Reduce/Restore/**Activate/Deactivate/Delete**/Finished | ✓ | Reduce/Restore only | 🔷 backup/activate flows deferred |
| Space accounting (Backups / Archives / Total / Grand Total) | ✓ | totals line only | 🔷 |

To reach parity the manager needs the deferred deactivate/activate/delete-game
**backup** subsystem and the two-list (mods ↔ save folders) layout with space totals.

## Checklist — remaining dialogs (pending this pass)

Each maps to its help topic; compare per the steps above.

| Port dialog | Help topic | Status |
|---|---|---|
| Main window (ribbon / menus / 3-pane) | `MsViewHelp` / `UserInterface` | ✅ (verified in earlier sessions) |
| Wizard Builder | `bhwizardbuilder.htm` | ⬜ |
| Workshop Viewer | `bhworkshop.htm` | ⬜ |
| Dependency Manager | `bhdependencymanager.htm` | ⬜ |
| Installation Analyser | `bhinstallationanalyser.htm` | ⬜ |
| Download Project | `bhdownloadproject.htm` | ⬜ |
| Publish Mod | `bhpublishmod.htm` | ⬜ |
| Folder Mapping (Map Files/Folders/Excludes) | `bhmapfiles.htm` / `bhmapfolders.htm` | ⬜ |
| Settings (General/Locations/Web) | `bhbasicsettings.htm` / `bhlocations.htm` | ⬜ |
| Portrait Manager | `rbportraitmanagerhelp.htm` | ⬜ |
| Start Screen Manager | `rbloadscreenhelp.htm` | ⬜ |
| Mods Played / Play Data | `bhmodsplayed.htm` | ⬜ |
| Conflicts Viewer | `managemodfileconflicts.htm` | ⬜ |

## Summary

Compared this pass: **3** dialogs. The ported **Character Explorer** now matches the
original's list / portrait / **Summary·Skills·Feats** structure. The **Doc Organiser**
carries all the core content with a different layout arrangement and a few deferred
extras. The **Game Saves Manager** is deliberately the archive-only slice and diverges
most (the full backup/activate manager is deferred).

Common cross-platform divergences recorded as **expected**: native Qt vs WinForms
widget chrome, push buttons vs icon toolbars, and macOS vs Windows fonts/spacing.
