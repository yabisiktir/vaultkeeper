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
`run_nit_shots.sh` uses the same sandbox and check: NIT's forms get neutral
constructor arguments and every prompt is answered automatically, and the
bottle's Documents folder is the real one.

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
| Main window | NIT reselects the mods that were selected when the profile last closed (`LoadSelections` / `SaveSelections`). | ✅ Saved per profile on close and profile switch; reselected on load. |
| All dialogs | NIT dialogs share one frame: a header (icon, description, round "?" help) and a footer (status text left; Save / Cancel right). VK dialogs put Help bottom-left and the description as plain text, with no header icon. | ⚖ Owner decision. Adopting NIT's frame reshapes every dialog, which `CLAUDE.md` asks not to do without a reason. |

## Second pass: the remaining forms (2026-09-28)

All 47 NIT forms now have a control dump (`nit/results.tsv` lists how each was
captured). Two harness changes made that possible:
- forms that close themselves in `Load` are dumped straight after construction;
- forms with no parameterless constructor are built with neutral arguments.

`vk_shots.py` also writes each Vaultkeeper screen's action list, and
`actions_diff.py` lists every NIT button, check box, menu item and tab with no
matching Vaultkeeper caption (`actions_diff.md`). That list is a prompt to check,
not a verdict; the verdicts are below. Many of NIT's never-shown renders come out
blank, so for those forms the dump is the reference.

| Screen | Finding | Status |
|---|---|---|
| Calculate CRCs (NIT `CalculateCRCs`) | NIT shows the file in hand, a progress bar and Cancel. VK showed a wait cursor only, and "all files" can take minutes. | ✅ Progress window with the mod, the file, "n of N" and Cancel. Cancelling keeps the checksums done so far; the rest keep their old values. |
| Create Installer (NIT `CreateInstaller`) | NIT shows the operation, the file and "n of N". VK showed nothing while extracting and copying. | ✅ Progress window fed by the build's phases. No Cancel: the old installer is already gone at that point, so stopping would leave a partial one. |
| Download Project, rules menu (NIT `TsRulePrefs`) | NIT has nine rule preferences; VK had one (project rules). | ✅ All of them, in NIT's order and words, on the rules button's drop-down and in Settings → Downloads. Each one off empties one table of the rules in force, as NIT does. |
| Crash Dump Manager | NIT's Submit shows the crash file and opens Beamdog's crash page. | ✅ Submit added; VK keeps its Open Folder too. |
| Find (NIT `FindDialogue`) | "Match whole word only" was missing. | ✅ Added, for text and for lists. |
| Pending Play Data | NIT's Clear erases all pending play times, after asking. | ✅ Added. |
| Doc Organiser | NIT's Reset discards pending name changes. | ➖ VK's Refresh already does this (it rebuilds from disk); its tooltip now says so. |
| Classes, Skills and Feats; Character Explorer | NIT's search steps through matches (Find Next / Previous); VK filters the list. Also NIT's Description button, where VK shows descriptions in a pane. | ➖ Same capability. |
| Create NWN Folder | NIT can make the chosen source the default "Copy from" folder. | ➖ VK takes the source from the profile each time and has no default-source setting. |
| Menu Item Editor | NIT edits one Run/Web item at a time, with a 35-character limit and a clipboard URL. | ➖ VK edits the items inline in Settings and checks the web links with its own command. |
| Game Manager Restore | NIT's separate restore window. | ➖ VK's Game Saves Manager has an Archived section with Restore and Delete Archive. |
| Movie conversion, RTF theme recolouring, Slide Show, NIT update | Progress or utility windows. | ➖ VK converts movies inside the installer build (now shown by its progress window); VK notes follow the theme, so no recolouring is needed; the Start Screen Manager has a Slide Show; self-update is deferred. |
| Screen Position Adjust | Positions NIT's pop-up message. | ➖ VK has no such pop-up. |
| Workshop Name Editor, Game Saves Path | NIT prompts. | ➖ Owner decisions: VK renames in the Workshop viewer (W9), and has no shared saves folder (logic audit). |
| NIT main window, Debug menu | Developer reports (Action List, Selection History, Text Scroll Position, title-bar colour…). | ➖ Developer tools, not user features. |

## Re-running

```bash
docs/screen_parity/run_nit_shots.sh [Form …]   # CrossOver "NIT" bottle; batches of ~12
docs/screen_parity/run_vk_shots.sh [Form …]
QT_QPA_PLATFORM=offscreen .venv/bin/python docs/screen_parity/pairs.py [Form …]
.venv/bin/python docs/screen_parity/actions_diff.py > docs/screen_parity/actions_diff.md
```
