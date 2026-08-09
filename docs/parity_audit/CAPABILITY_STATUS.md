# Capability sweep — the original's help topics against this port

The other parity instruments all anchor on **things already ported**, and so
cannot find a capability that was never started. One duly hid for months: NIT's
first run asks seven setup questions, and the port asks two. It has no form of
its own, no Help button, and lives inside two form-event handlers, so the dialog
sweep, the Help-button pass and the method ledger each had a reason to miss it.

This sweep uses the **236 help topics** as the denominator instead — one topic,
one thing a user can do. Run `capability_sweep.py` to list what has not been
given a verdict yet; verdicts live here, in prose, so the reasoning travels with
them.

## Reviewed

| Topic | Capability | Verdict |
|---|---|---|
| firsttimeexecution.htm | Run the Installer Tool for the first time | **Partly closed** — the two silent-failure questions are asked; five remain, see below |
| bhnitdownload.htm | Update the Installer Tool | GAP (see below) |
| mstoolbareditorhelp.htm | Customise the Quick Access Toolbar | GAP (see below) |
| syncmods.htm | Synchronise networked PC Mods | Non-goal — the shared store; mod export/import is ported instead |
| createcheckpoints.htm | Create Checkpoints | Ported (`controller.create_checkpoint`) |
| compressmodfolders.htm | Compress or Uncompress Mod folders | Ported (Manage menu) |
| createrestorers.htm | Create Restorers | Ported |
| originalrestorers.htm | Create Original Restorers | Ported |
| createcharrestorers.htm | Create Character Restorers | Ported — after this file recorded it wrongly once; see below |
| workwithinstallationsets.htm | Work with Installation Sets | Ported (Installation Manager) |
| anneal.htm | Validate conflicting files (Anneal) | Ported |
| removeerffiles.htm | Remove ERF Files | Ported |
| removeillegalmodfiles.htm | Remove illegal Mod files | Ported |
| rebuilddatabase.htm | Rebuild Database | Ported |
| recovergroup.htm | Recover Group information | Ported |
| recovermodproperties.htm | Recover Mod Property information | Ported |
| calculatecrcs.htm | Calculate checksum values | Ported |
| databackups.htm | Backup and Restore the Installer Tool's data | Ported (Backup and Export Manager) |
| newtopic51.htm | Send diagnostic information to Surazal | Ported (menu entry) |
| bhdownloadproject.htm | Download and install Vault Projects | Ported — see `docs/vault_downloads.md` |
| exportedmods.htm | Export and Import Mods | Ported (`.vkmod`) |
| exportedsettings.htm | Export and Import Settings | Ported |
| newtopic46.htm | Use the Mod Selector to navigate to a Mod | Ported (`main_window.py:243`) |
| newtopic65.htm | Reset Window Layout | Ported (`MsResetWindow`) |
| newtopic73.htm | Show BioWare's Portrait Images | Ported (`MsOriginalPortraits`) |
| newtopic76.htm | Clear Extracted Hak Portraits | Ported (`MsClearHakPortraits`) |
| newtopic55.htm | Move files to the Development folder | Ported (`MsMoveToDev`) |
| newtopic12.htm | View Download Rules | Ported (`MsOpenRulesFile`) |
| newtopic2.htm | Create NIT Mods from Restorers | Ported (`MsConvertRestorer`) |
| bhworkshop.htm | Manage Steam Workshop Subscriptions | Ported (`MsWorkshopViewer`) |
| saveinifiles.htm | Save your customised INI files | Ported (the five Ini File commands) |
| newtopic58.htm | Import Map Settings | Deferred — recorded in DIALOG_PARITY as the map pages' import context menu |
| newtopic35.htm | Quick Access Toolbar | GAP — see above |

## The first-run gap, in detail

`firsttimeexecution.htm` describes seven questions. The port asks two — it
detects the installs, silently takes the first, names a profile after the
edition, and offers a legacy import.

| # | NIT asks | Port |
|---|---|---|
| 1 | Which library, when several Enhanced Edition installs are found (Steam, Beamdog, GOG) | **Asked** — first-run screen, preselecting the first |
| 2 | Which edition is installed, when NWN cannot be found | Falls back to a folder picker |
| 3 | Where the EE user-files folder is, when it cannot be located — plus *Disable Enhanced Edition detection at start-up* | Auto-resolves; no prompt, no setting |
| 4 | Which drive/folder for the store, **recommending the one with most free space** | **Asked** — preselecting the roomiest *local* volume |
| 5 | **Player or Mod Builder**, which seeds the installer exclusion preferences | Never asked; defaults used |
| 6 | Group Set preference, when the default profile initialises | Never asked |
| 7 | Whether to create Restorers for the default profile | Never offered (the command exists) |

Questions 1 and 4 were the ones with teeth — each produced a wrong result in
silence — so those two are now asked, on one screen, both pre-answered, and only
when there is genuinely more than one answer. A machine with a single install
and a single volume still sees nothing.

The recommendation skips **network volumes**, however roomy. The machine this
was built on offers three NAS shares of 493 GB each against a 26 GB system disk;
recommending one would put the whole profile behind a mount that is not always
there. They stay in the list for anyone who means it.

The remaining five are all reachable from Settings and none of them fails
silently: the edition and user-folder prompts have working auto-detection behind
them, Player-vs-Builder and the group set have defaults, and *Create Restorers*
is a command on the menu.

## Other gaps this sweep found

* **Self-update** (`bhnitdownload.htm`) — NIT downloads and installs its own
  updates. This port has no updater at all. Arguably a non-goal for something
  distributed as a GitHub release, but it was never *decided*, only absent.
* **Quick Access Toolbar customisation** (`mstoolbareditorhelp.htm`) — the port
  has a fixed ribbon and toolbar.

## The command sweep — 197 of 209

Every command in the original carries a control id (`MsInstall`, `TsFind`, …),
and the port carries the same ids, so the two sets can simply be diffed. Pulled
from `NIT.Designer.vb`: **209 commands, 197 present in the port.** The twelve
absent:

| Absent | What it is |
|---|---|
| `TsQuick`, `TsStatus` | Toolbar containers — the designer's `ToolStrip1` placeholder captions, not commands |
| `MsCancelGoTo`, `TsSelectGroupName` | *Cancel* buttons on two dialogs |
| `MsGroupNone`, `MsPlayedInfo` | Runtime-filled labels (*None*, *Mod played for 28 hours*), not commands |
| `TsbModSelector` | **Present** — a combo box, not a menu item, so the id-based diff missed it (`main_window.py:243`) |
| `MsGetUpdate` | Self-update. A real gap, above |
| `MsCopyToShared` | Shared NIT Store — non-goal |
| `MsTitleBarColour` | A Win32 DWM attribute |
| `MsValidateOnActivateStatus` | Status-bar toggle for validate-on-activate |
| `MsSaveNwnInfo` | *Recreate original NWN file information* — regenerates the bundled original-file checksum table from a clean, unmodded install. A maintainer's tool; the port ships the table as JSON and cannot rebuild it |

So at the command level the port is effectively complete, and the two
instruments cover different things: this one finds missing **commands**, the
help-topic sweep finds missing **flows and behaviours**. The first-run gap has
no command, which is precisely why it needed the other one.

## Keyboard shortcuts

`keyboardshortcuts.htm` documents fifteen main-window shortcuts. The port had
**none** — the topic shipped with the application describing keys that did
nothing. Fourteen are now bound in `menu_bar.SHORTCUTS`, every one to a command
that already existed; only Ctrl+O is left out, because VB's "open the selected
file with its associated program" acts on the Contents pane and a window-wide
binding would fire it with a mod selected and nothing to open.

### On macOS

Qt maps portable `Ctrl` to Command by itself, so `Ctrl+G` is already ⌘G and
nothing needed translating. Two things it cannot fix were handled explicitly:

* **F1 and F2 never reach the application** on a default Mac — they are media
  keys unless "Use F1, F2, etc. as standard function keys" is on, which it is
  not by default. So `MAC_EXTRA_SHORTCUTS` *adds* Return for Rename (Finder's
  convention) and `StandardKey.HelpContents` for Help (⌘?). Added, not
  substituted: whoever has enabled function keys keeps the documented key.
* **Two menu items say "Settings"** — Basic and Advanced. macOS picks its
  Preferences entry out of the menus by caption, so the heuristic had two
  candidates for one slot and could have emptied both out of the Options menu.
  `MAC_MENU_ROLES` names Advanced Settings as Preferences and leaves Basic
  Settings where it is.

⌘Q and ⌘, are deliberately **not** bound by hand: Qt attaches them once a role
is set, and `Ctrl+Q` means nothing on Windows.

Not changed, though flagged: ⌘M (New Mod) collides with the system Minimize
idiom, ⌘G (New Group) with Find Next, and ⌘±  with Zoom. Nothing in this
application competes for any of them, and all three are in the original's
documented shortcut table — deviating from documented behaviour to chase an
idiom costs more than it buys.

Worth knowing for anyone testing these: **Qt does not deliver shortcuts under
the offscreen platform**, so the suite can only assert the binding. Firing was
checked on a real platform through the CrossOver bottle.

## The Options menu's housekeeping commands

Eight sat on the menu greyed out as "not yet available". Reviewed as a cluster:

| Command | Verdict |
|---|---|
| `MsResetWindow` — Reset Window Layout | **Ported.** Forgets the saved geometry *and* puts the splitters back; forgetting the geometry alone leaves the panes where they were dragged, which is usually what went wrong |
| `MsClearWaitCursors` | **Ported.** An override cursor outliving its work makes the whole app look hung; this is the escape hatch |
| `MsClearSelectionHistory` | **Ported.** Empties Recent Mods |
| `MsClearScrollInfo` — Clear Text Position Information | Not applicable: it clears remembered scroll positions in VB's text viewers, and this port does not remember any |
| `MsResetWebMenu` — Reset Web Menu Icons | Not applicable: it re-fetches favicons for the Web menu, and this port does not fetch them |
| `MsResetTaskbarIcon` | Not applicable: a Windows taskbar/jump-list concern |
| `MsPropertiesHeight` — Automatic Properties Panel Height | Open. A real preference: auto-size the properties pane rather than leaving it where the splitter sits |
| `MsUpdateEeFiles` — Update Enhanced Edition Files | **Open, and the largest of the eight.** No controller support at all |

## Not yet reviewed

Everything else. `capability_sweep.py` lists them; the remaining topics are
mostly per-screen guidance already covered by `DIALOG_PARITY.md`, but that is an
expectation rather than a finding, which is exactly the distinction this file
exists to keep.

## The behaviour sweep — what a command diff cannot see

`behaviour_sweep.py`, added after the play-time readout turned out to be missing
and the command diff had called the port 197/209 complete. A command diff reads
a menu item's id. It cannot see a behaviour with **no caption, no menu entry and
no help button** — a right-click, a double-click, a keypress — and four gaps had
by then been found by hand and none by a tool.

`--behaviours` lists every such handler in the original: **32**, small enough to
read to the end. Reviewed:

| Where | Behaviour | Port |
|---|---|---|
| Mod list | **Double-click a mod → Install, or Uninstall if installed** | **GAP** — everyday interaction, entirely absent |
| Character status icon | Right-click → Character Summary | **GAP** |
| Play ribbon button | Right-click → Start Screen Manager (Ctrl: preview the installed screen; Shift: auto loadscreen) | **GAP** |
| Portrait Manager command | Right-click → open the portrait image web page | **GAP** — and the setting it needs (`portrait_image_web_page`) is one nothing reads |
| Character Explorer skills/feats | Double-click → the description | Different shape: shown in a panel beside the list |
| Play Data Viewer game row | Right-click → set the start date | **Ported** (this session) |
| Character status icon | Right-click → Character Summary | **Ported** |
| Play ribbon button | Right-click → Start Screen Manager | **Ported** |
| Portrait Manager command | Right-click → the portrait image web page | **Ported** — and its setting is read at last |
| Recycle toggle | Right-click → open the Trash | **Ported** |
| Select Text File icon | Right-click → Documentation Organiser | **Ported** |
| Wizard Report icon | Right-click → Wizard Builder | **Ported** |
| Installation Analyser — file row | Double-click → Properties | **Ported** |
| Installation Analyser — folder row | Double-click → Open Folder | **Ported** |
| Find and Rename — mod row | Double-click → load the name into Find *and* Replace | **Ported** |
| Portrait Manager — portrait row | Double-click → Edit Portrait | Already ported |
| Character Explorer skills/feats | Double-click → the description | Different shape: shown in a panel beside the list |

**All 32 reviewed.** Every one is either ported or recorded above with the reason
it is not.

Reviewing those turned up something none of the three sweeps was looking for:
**the status bar's icons were connected to nothing at all**. Ten of its eleven
signals were emitted into the void, so every icon but *Mods* was dead to the
click — including the pending-changes icon, whose own tooltip promises to
"display details about files added, removed or changed". A signal with no
receiver is the same shape of defect as a setting with no reader, and a test now
fails if any of them goes unconnected again.

## A verdict this file got wrong

`createcharrestorers.htm` was recorded as Ported. It is not: there is no way to
create a Character Restorer here at all. The evidence that convinced me was a
grep for `character_restorer`, which matched **a constant** —
`CHARACTER_FILES_RESTORER`, one of the three original-file restorers — and not
the feature. Grep evidence is weak in both directions, and this file exists to
hold verdicts, so a wrong one is worse than an unreviewed one.

It mattered twice over: `auto_character` could not be wired until the feature it
switches on existed. Both are done now — the wrong verdict is left here on
purpose, because how it was reached is the useful part.

## Settings that do nothing

`--settings` lists preferences this port writes and never reads. A preference
someone can tick that changes nothing is worse than a missing one, because it
lies. It found `startup_sound` (since fixed) and, still open, **eight**:

**Five are now wired**: `validate_game_config_on_startup` (the startup check ran
unconditionally, so the box could not be unticked), `select_game_mod`,
`copy_mod_name_on_play`, `copy_debug_mode_on_play` (all three read when Play is
pressed) and `installer_restore` (rebuilding an installed mod's payload now puts
it back, so the game stops running the files that were just replaced).

**The list is now empty**: `behaviour_sweep.py --settings` reports zero. Every
preference the port offers changes something.

`auto_character` is wired too, now that Character Restorers exist: closing the
game saves the character just played, but only when there is exactly one with no
owner. Several is a question about which build belongs to which mod, and that is
not a question to put to somebody who has just shut the game down.

`hak_item_icons` and `exact_item_icons` were a **false positive**: both are read
by the save editor through its host protocol, and the sweep scanned only this
package. Fixed — it reads both now.
