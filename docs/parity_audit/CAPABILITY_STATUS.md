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
| firsttimeexecution.htm | Run the Installer Tool for the first time | **GAP — the largest found.** See below. |
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

## The first-run gap, in detail

`firsttimeexecution.htm` describes seven questions. The port asks two — it
detects the installs, silently takes the first, names a profile after the
edition, and offers a legacy import.

| # | NIT asks | Port |
|---|---|---|
| 1 | Which library, when several Enhanced Edition installs are found (Steam, Beamdog, GOG) | **Takes `installs[0]` without asking** |
| 2 | Which edition is installed, when NWN cannot be found | Falls back to a folder picker |
| 3 | Where the EE user-files folder is, when it cannot be located — plus *Disable Enhanced Edition detection at start-up* | Auto-resolves; no prompt, no setting |
| 4 | Which drive/folder for the store, **recommending the one with most free space** | Uses the platform default silently |
| 5 | **Player or Mod Builder**, which seeds the installer exclusion preferences | Never asked; defaults used |
| 6 | Group Set preference, when the default profile initialises | Never asked |
| 7 | Whether to create Restorers for the default profile | Never offered (the command exists) |

Questions 1 and 4 are the ones with teeth: picking the wrong install of three
silently attaches the profile to a game folder the user does not play, and the
store lands on whatever drive the platform default names, which on a small SSD
with mods on a large HDD is the wrong one.

## Other gaps this sweep found

* **Self-update** (`bhnitdownload.htm`) — NIT downloads and installs its own
  updates. This port has no updater at all. Arguably a non-goal for something
  distributed as a GitHub release, but it was never *decided*, only absent.
* **Quick Access Toolbar customisation** (`mstoolbareditorhelp.htm`) — the port
  has a fixed ribbon and toolbar.

## Not yet reviewed

Everything else. `capability_sweep.py` lists them; the remaining topics are
mostly per-screen guidance already covered by `DIALOG_PARITY.md`, but that is an
expectation rather than a finding, which is exactly the distinction this file
exists to keep.
