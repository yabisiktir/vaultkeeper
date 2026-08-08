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
| createcharrestorers.htm | Create Character Restorers | Ported |
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

## Not yet reviewed

Everything else. `capability_sweep.py` lists them; the remaining topics are
mostly per-screen guidance already covered by `DIALOG_PARITY.md`, but that is an
expectation rather than a finding, which is exactly the distinction this file
exists to keep.
