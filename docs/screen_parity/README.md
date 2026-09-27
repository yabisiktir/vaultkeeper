# Screen parity

Does each Vaultkeeper screen give the NIT user what NIT's screen gave them? The
bar is *structural*, not pixel-level: the same controls and captions, NIT's own
icons and toolbar idiom (the UX identity rule), and every action NIT's screen
offers. Vaultkeeper's own layouts and extra controls stay (see `CLAUDE.md`:
Vaultkeeper is the baseline and may do more, but never less).

## Method

| Step | Tool | Output |
|---|---|---|
| Inventory every NIT form and its VK counterpart | `inventory.py` | `inventory.md` |
| Render NIT's forms and dump their control trees | `run_nit_shots.sh` (the logic-audit harness's `screenshot` query, in the CrossOver bottle) | `nit/<Form>.png`, `nit/<Form>.controls.txt` |
| Render VK's counterpart of each form | `run_vk_shots.sh` → `vk_shots.py` | `vk/<Form>.png` |
| Put the two side by side | `pairs.py` | `pairs/<Form>.png` |

The control dumps are the reliable reference: they list every control, caption,
toolstrip item, shortcut, and whether it is hidden. Some NIT renders are
incomplete because `DrawToBitmap` skips owner-drawn controls (the main window's
file view, the Game Saves Manager's lists).

### Safety: rendering is not read-only

Building Vaultkeeper's windows runs real logic. Opening the Game Saves Manager
backs up other games' saves, for example. On 2026-09-28 an early, unisolated
version of `vk_shots.py` did that against the real `Documents/Neverwinter
Nights` and lost two of the owner's saves. So there are now two guards:

1. `vk_shots.py` isolates itself like `tests/conftest.py`. It sets HOME and the
   config variables to a temp folder, patches `_home`, redirects the recycle bin
   and builds its own user folder. It refuses to run if the game folder resolves
   outside that temp folder.
2. `run_vk_shots.sh` runs it under a macOS sandbox profile (`no_real_nwn.sb`)
   that denies any write to the real NWN user folder and the real store. It also
   compares a listing of both before and after, and fails loudly if either
   changed.

Always render through `run_vk_shots.sh`, never `vk_shots.py` directly.

## Findings (2026-09-28)

Legend: ✅ fixed in this pass · ➖ VK differs deliberately or does more · ⚖ owner decision

| Screen | Finding | Status |
|---|---|---|
| Installation Manager | NIT's action toolstrip (Checkpoint, Create Set, Rename, Prune, Delete, Sort By ▾, Selector, with icons) was a column of text buttons plus a sort combo; the Group Selector sat in a third column rather than under the set list. | ✅ Now NIT's toolstrip with NIT's icons, Sort By as a drop-down (Created/Updated/Name, Ascending/Descending), and the Group Selector under the sets. |
| Main window notes pane | NIT's `RichTextToolbar`: Open with WordPad (Ctrl+O), Cut, Copy, Paste, Paste as Text (Ctrl+T), Bold, Italics, Underline, Strikeout (Ctrl+K), Font Colour, Undo, Redo, Select All, Find. VK's bar had only the formatting buttons, with other icons. | ✅ NIT's buttons in NIT's order, with its icons (from the LazWorks library) and keys. "Open with WordPad" opens the notes in the system's RTF editor; edits there reload when VK is next activated. VK's font, size, highlight, alignment and clear-formatting stay, after NIT's buttons. The glyph icons are lightness-inverted on a dark palette. |
| Hak Patch Editor | NIT's Move Up / Move Down carry blue arrows and Ctrl+Up / Ctrl+Down (on the list's context menu). VK's buttons had neither. | ✅ Arrows, keys and the context menu added; VK keeps its visible buttons as well. |
| Alias Section Editor | NIT lists the aliases alphabetically; VK used file order. | ✅ Sorted. |
| Alias Section Editor | NIT's Delete (custom alias file) and the "(Shared by all Profiles)" SAVES note belong to features VK does not have. | ➖ Deliberate (logic audit stage 4: `SetGameSaves`, custom alias definitions). |
| Mod Explorer | With every filter on one row, the name filter was squeezed to a sliver at the dialog's normal width. | ✅ Two rows: NIT's toolstrip row (filter, Filters…, Mod Files / Installers / Restorers, Filters On), then the play-data filters. |
| Mod Explorer | A mod with no module file is hidden while "Mod Files" is ticked. | ➖ Faithful to NIT (`TsModFiles`). |
| Create Missing Installers | Primary button reads "Save" when nothing is left to create, else "Create". | ➖ Faithful to NIT. |
| Find Profile Files | NIT's "Find what" is a combo box; VK has a text box plus whole-word and match-case options. | ➖ VK does more. |
| User Response Editor | Same four categories, different order. | ➖ Cosmetic. |
| Game Saves Manager, Download Project, Settings, Workshop Viewer, Publish Mod, Wizard Builder, Dependency Manager, Backup Manager, Mod Play Viewer, Installation Analyser | Same actions or more (the Settings depth, Mod Play Viewer and Dependency Manager gaps were closed in earlier passes: see `docs/PARITY.md` and `docs/parity_audit/`). | ➖ |
| All dialogs | NIT dialogs share one frame: a header (icon, description, round "?" help) and a footer (status text left; Save / Cancel right). VK dialogs put Help bottom-left and the description as plain text, with no header icon. | ⚖ Owner decision. Adopting NIT's frame reshapes every dialog, which `CLAUDE.md` asks not to do without a reason. |

## Re-running

```bash
docs/screen_parity/run_nit_shots.sh        # needs the CrossOver "NIT" bottle
docs/screen_parity/run_vk_shots.sh [Form …]
QT_QPA_PLATFORM=offscreen .venv/bin/python docs/screen_parity/pairs.py [Form …]
```
