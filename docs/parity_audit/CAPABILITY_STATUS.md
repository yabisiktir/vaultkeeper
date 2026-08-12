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
| bhnitdownload.htm | Update the Installer Tool | **Was a GAP, now closed** — checks releases, offers the page |
| mstoolbareditorhelp.htm | Customise the Quick Access Toolbar | **Was a GAP, now closed** (`MsCustomise`) |
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
| databackups.htm | Backup and Restore the Installer Tool's data | Ported — Backup/Restore Data always worked; the *Manager* did not exist until now |
| newtopic51.htm | Send diagnostic information to Surazal | Ported (menu entry) |
| bhdownloadproject.htm | Download and install Vault Projects | Ported — see `docs/vault_downloads.md` |
| exportedmods.htm | Export and Import Mods | Ported (`.vkmod`) |
| exportedsettings.htm | Export and Import Settings | Ported |
| newtopic46.htm | Use the Mod Selector to navigate to a Mod | Ported (`main_window.py:243`) |
| newtopic65.htm | Reset Window Layout | Ported (`MsResetWindow`) |
| newtopic73.htm | Show BioWare's Portrait Images | **Said Ported and was not** — built now (`MsOriginalPortraits`) |
| newtopic76.htm | Clear Extracted Hak Portraits | Ported (`MsClearHakPortraits`) |
| newtopic55.htm | Move files to the Development folder | **GAP** — this file said Ported; it was not. See below |
| newtopic12.htm | View Download Rules | Ported (`MsOpenRulesFile`) |
| newtopic2.htm | Create NIT Mods from Restorers | Ported (`MsConvertRestorer`) |
| bhworkshop.htm | Manage Steam Workshop Subscriptions | Ported (`MsWorkshopViewer`) |
| saveinifiles.htm | Save your customised INI files | Ported (the five Ini File commands) |
| newtopic58.htm | Import Map Settings | Deferred — recorded in DIALOG_PARITY as the map pages' import context menu |
| newtopic35.htm | Quick Access Toolbar | **Closed** — contents editable, `MsShowText` wired |
| useattributefilters.htm | Use Attribute Filters | **Was a GAP, now closed** — Mod Files / Installers / Restorers |
| commandline.htm | Command Line Options | **Was a GAP, now closed** — all five, plus the start-up keys |
| findoperations.htm | Perform Find Operations | **Was partly ported** — Find is focus-scoped now, not always the profile search |
| findinprofile.htm | Find files in your Profile | Ported (Find Files dialog) |
| findfiles.htm | Find files in Contents or Details | **Was a GAP, now closed** — Find steps through list rows |
| findtext.htm | Find text within a file | **Was a GAP, now closed** — Find bar + a Find button on the viewer |
| filterbynotes.htm | Filter by Notes | Not applicable — `ModData` carries no notes field here |
| dealwithmodupdates.htm | Deal with Mod updates | **Now complete** — Move to Folder and Move to History were the missing steps |
| bhmodsplayed.htm | Mods I have not played for a long time | Ported (`MsModsPlayed`) |
| usealtkey.htm | Use Alt-Key shortcuts | Ported — every menu title carries its mnemonic, and Qt does the rest |
| automaticbackupofgamesaves.htm | Automatic backup of Game Saves | **Was a GAP, now closed** — runs when the manager opens |
| bhgamemanager.htm | Work with Game Saves | Ported (Game Saves Manager) |
| bhgamemapper.htm | Link Game Save to Mod name | Ported (the play loop's prompter) |
| defaultgroupsets.htm | Default Group Sets | **Was a GAP, now closed** — the third first-run question |
| faqgroupnumbers.htm | Why are the default Groups numbered? | Closed with it — the numbers are the install order |
| dealwithexisting.htm | Deal with existing installed Mods | Ported — the pieces it strings together all exist (INI save, Create Original Restorers, import) |
| faqothertools.htm | Mods installed with other tools | Ported (Create Restorer, twice — before and after the external tool) |
| customisefonts.htm | Customise Fonts | **Bounded port, now wider** — family + size, not VB's 11 per-element fonts |
| customisecolours.htm | Customise Colours | **Bounded port, now wider** — the 4 colours this app paints with, not VB's 25 |
| customisetheinstallertool.htm | Customise the Installer Tool | Ported — Basic and Advanced Settings both reachable from Options |
| customisemodinstallers.htm | Customise Mod Installers | Ported — Map Excludes, Wizard Builder and the review flow all exist |
| bhbackupmanager.htm | Work with backups and exports | **Was a GAP, now closed** — the menu item did nothing |
| newtopic18.htm | Automate Mod dependency definition | **Closed** — Auto, with progress + Cancel and the follow-up offer |
| validatedatabase.htm | Perform validation tasks | **Closed** — the last of the five, Validate Neverwinter Nights (`MsValidate`) |
| newtopic51.htm | Send diagnostic information | **Now real** — was a menu entry only; gathers versions/paths/log |
| newtopic23.htm | Manage Workshop Mods | Ported — `MsRefreshWorkshopFiles` is wired now too |
| The New File trio | `MsNewFolder` / `MsNewTextFile` / `MsNewRtfFile` | **Was a GAP, now closed** |
| newtopic67.htm | Clear Text Position Information | **Was a GAP, now closed** — needed the memory it clears |
| newtopic42.htm | The close button is missing | **N/A by design** — see below |
| updatedeefiles.htm | Update Enhanced Edition Files | **Was a GAP, now closed** (`MsUpdateEeFiles`) |
| Toolbar editor | `MsCustomise` / `MsShowText` | **Was a GAP, now closed** |
| newtopic78.htm | Reset Web Menu Icons | **Closed as far as it applies** — no favicons here, so the link check is all of it |
| newtopic47.htm | Use Recent Mods to navigate to a Mod | **Closed** — Pin / Unpin / Remove |
| newtopic28.htm | Mod List | **Closed** — the status icon installs/uninstalls |
| switchinggamesaves.htm / restoregamesavesfrombackup.htm | Right-click Activate | **Closed** — brings the mod with it |
| mscharacterviewer.htm | Use the Character Explorer | **Closed** — the Select button was the last piece |
| defineextension.htm | Define an extension map | **Closed** — secondary folder + exceptions are editable |
| statusicons.htm | Mod and File Status Icons | **Was a GAP, now closed** — the eleven meanings, on the rows that show them |
| newtopic34.htm | Status Bar | **Was a GAP, now closed** — two dead signals + Selection Preferences |
| newtopic63.htm | Clear Selection History | **Was wrong, now right** — it cleared Recent Mods |
| rbportraitmanagerhelp.htm | Use the Portrait Manager | Ported — toolbar, keys and the image-strip click zones all present |
| rbloadscreenhelp.htm | Use NWN's Start Screen Manager | **Ported bar the clickable status texts**, now added |
| newtopic4.htm | Review and customise download information | **Ported bar multi-select + Space**, now added |
| filterbymodstate.htm | Filter by Mod State | Ported — the =/>/< operands, in the help's own wording |
| definenewprofiles.htm | Define new Profiles | **Closed** — the edition is asked and fixed, and the Profiles page lists them |
| newtopic10.htm | Ribbon | Ported — the seven tabs, in the original's order |
| recordamodswebpagelink.htm | Record a Mod's Web Page Link | **Ported bar the Add Link affordance**, now added |
| movenonnitfolders.htm | Move non-NIT Mod folders in | Ported — paste folders into the selected group |
| addanewmod.htm | Add a new Mod | **Ported bar the group choice**, now added |
| filterbyrating.htm | Filter by Rating | Ported — Matches / Worse than / Better than |
| newtopic6.htm / newtopic14.htm | Download and Install files / Wizard for Custom Menus | Ported |
| newtopic21.htm | Build a Wizard using Archive Folders | **Was a GAP, now closed** — the View box's archive views |
| newtopic25.htm / newtopic26.htm | Windows Title Bar / Menu Bar | Ported — including the play-time hover, click, right-click and Ctrl+click |
| managemodfileconflicts.htm | Manage Mod file conflicts | Ported — list order decides, and uninstall re-anneals |
| makemodnotesandrecordinformation.htm | Make Mod notes | Ported (Mod Properties + Notes) |
| newtopic1.htm | Create Restorers to backup installed Files | Ported |
| tshelpfindandrename.htm | Find and rename Mods | **Ported bar selecting the matches**, now added |
| createmissinginstallers.htm | Create missing Mod Installers | Ported — including the include-excluded toggle |
| deletinggamesaves.htm | Delete Game Saves | **Was a GAP, now closed** — the Finished button, and its own recycle preference |
| specifyaneverwinternightsfolder.htm | Specify a Neverwinter Nights folder | **Closed** — per-profile paths, editable on the Profiles page |
| createaneverwinternightsfolder.htm | Create a Neverwinter Nights folder | **Closed** — on the Profiles page, per profile |
| newtopic24.htm | Update existing Mods | Ported — the superseded-downloads prompt offers Delete and _History |
| communitypatchprojectcpp.htm | Community Patch Project (CPP) | **Led to a real gap** — the exclusions its advice depends on did not exist |
| communityexpansionpackcep.htm | Community Expansion Pack (CEP) | Advice; nothing to port |
| removeaprofile.htm | Remove a Profile | **Was a GAP, now closed** — there was no way to remove one |
| switchextendededition.htm | Switching Beamdog ↔ Steam | Ported — the Library path is editable on Locations |
| essentials.htm / newtopic.htm | Terminology / uninstalling NIT | Reference; nothing to port |
| movingmodsfromonegrouptoanother.htm | Moving Mods between Groups | **Ported bar "None"**, now added |
| deletearchives.htm | Delete archived Game Saves | **Was a GAP, now closed** — I had marked this Ported off the Restore button; there was no Delete at all |
| newtopic13.htm / newtopic72.htm / reviewmodinformationinaddedfiles.htm | Download rules, best practice, Doc Organiser | Advice for features that exist |
| newtopic20.htm | Detect Steam Workshop Subscriptions | **Ported bar load-time detection**, now added |
| newtopic22.htm | Disable Workshop management | **Was a GAP, now closed** — Stop Managing, keeping or deleting the copies |
| createmodinstallationsets.htm / uninstallinstallationsetdefinedm.htm | Installation Sets | Ported (Installation Manager) |
| renameaprofile.htm | Rename a Profile | **Was a GAP, now closed** |
| newtopic17.htm | Use Download Project to define dependencies | **Was a GAP, now closed** — they were downloaded and discarded |
| addorremovegroups.htm / updaterestorers.htm | Installation Set groups / Update Restorers | Ported |
| newtopic5.htm | Work with Download Rules | **Was partly ported** — rules applied and exclusions reported, but the only way to turn them off was three dialogs away; now a toggle on the Download Project dialog |
| msconflicts.htm | Mod File Conflicts | **Was answering a narrower question** — it read the installed list, so an uninstalled mod reported no conflicts; now reads the installers, with the topic's Selected/Installed/All buttons |
| newtopic40.htm | Rename a document | Ported (Doc Organiser's Rename / Rename To) |
| openagamesavefolderwithwindowsfi.htm | Open a game save folder with File Explorer | **Was partly ported** — only the icon existed; the double-click, right-click and Ctrl+O the topic names did not |
| newtopic60.htm | Display Character Summary Information | **Was partly ported** — the button existed; the right-click the topic describes did not |
| adddownloadedfilestoamod.htm | Add downloaded files to a Mod | **Was partly ported** — Add Files always copied; the Use Move preference (VB default: move) did not exist |
| keyboardshortcuts.htm | Keyboard Shortcuts | **Was partly ported** — the main window's 14 were right; Ctrl+O had no command behind it at all, and the Game Saves Manager's own four were missing |
| filterbystartendorhenchman.htm | Filter by Start, End or Henchman | Ported (`mod_explorer._passes_number`, all four rules incl. the bare operator) |
| bhpreferences.htm | Specify your Preferences | **Was partly ported** — the page existed; "changed this session is shown in italics" did not, so nine tabs had to be re-read to see what you were saving |
| bhwebmenu.htm / bhrunmenu.htm | Customise the Web / Run menu | **Mostly ported, two gaps closed** — a new entry appended instead of landing after the selected one, and right-click did nothing. The ampersand Alt-key works for free (Qt reads it) |
| reducefileclutter.htm | Reduce file clutter | **Half ported** — Move to Downloads was there, "view the contents of compressed files" was not; now reads the archive index |
| restoringdeletedsavesfromtherecy.htm | Restoring deleted saves from the Recycle Bin | **Was a GAP, now closed** — the preference existed but only Finish Game read it, so backups and archives went permanently whatever it said |
| downloadandinstallmods.htm | Download and install Mods from other sites | An index of steps whose commands are each ported |
| newtopic27.htm | Profile Name | **Was a GAP, now closed** — the name was shown nowhere; click it to refresh |
| newtopic33.htm / newtopic64.htm | Properties Panel / Automatic Height | **Was a GAP, now closed** (`MsPropertiesHeight`) |
| newtopic49.htm / newtopic50.htm | Right-clicking the Profile Name / Mod's right-click menu | N/A — image-caption stubs with no content of their own |
| bhmapexcludes.htm / bhmapextensions.htm / bhmapfiles.htm / bhmapfolders.htm | The four map pages | Ported (Folder Mapping's four tabs) |
| bhadvanced.htm / bhlocations.htm / bhpreferences.htm / bhprofiles.htm | Settings pages | Ported (Settings tabs) — a bulk verdict; see bhwebmenu/bhrunmenu for what one of these hid |
| bhaliaseditor.htm | Use the Alias Section Editor | Ported (`MsAliasSection`) |
| bhdocmanager.htm | Organise Mod Documentation | Ported (`MsDocOrganiser`) |
| bhhelp.htm | Change the Hak Patch sequence | Ported (`MsHakPatchEditor`) |
| bhinstallationanalyser.htm / bhinstallationmanager.htm / bhpublishmod.htm / bhwizardbuilder.htm / bhdependencymanager.htm / bhbasicsettings.htm | Their screens | Ported |
| faqnitcrashes.htm | The Installer Tool crashes every time I start it | Closed with the above — the topic is a pointer to the two below |
| corruptedprofiledata.htm | Corrupted Profile Data | Closed — `-RestoreProfileData` / hold Alt |
| corruptedsettings.htm | Corrupted Settings | Closed — `-Settings` / the start-up menu |
| usegroupfilters.htm | Use Group Filters | Ported (the Filters… dialog + Undo Group Changes) |
| usemodprefixfilters.htm | Use Mod Prefix Filters | Ported (prefix list + Undo Prefix Changes) |
| usefilterboxestospecifyfiltering.htm | Use Filter Boxes to specify filtering criteria | Ported except the Notes filter — `ModData` carries no notes here |

## The Mod Explorer's filters

Four topics, reviewed together because they describe one subsystem. Three were
already ported. The fourth, **attribute filters**, was missing outright and is
the same shape as the first-run gap: a toolbar of three toggles, no dialog of
its own, no command id — invisible to both the other sweeps.

They are *Mod Files*, *Installers* and *Restorers*, and all three are on by
default, so the original's Mod Explorer opens showing only mods that can be
played and have an installer. Two details are worth keeping in mind because
they look like mistakes:

- **The Installers switch reads two different ways.** Ticked, it keeps mods
  that *have* an installer folder; unticked, it hides mods that *are* an
  installer (`NotFiltered` tests `HasModInstaller` in one branch and
  `IsInstaller` in the other).
- **`HasModInstaller` is the folder, not the identifier file.** Our
  `ProfileData` had a `mod_installer_exists` hook for this that nothing ever
  passed, so it had been silently falling back to the identifier file. The
  report now tests the folder, as VB does. A hook with no caller is the same
  defect shape as a setting nothing reads.

Also here: **Filters On/Off** (`TsIgnoreFilters`), one switch that suspends
every filter without clearing any of them.

## Player or Mod Builder — the fourth first-run question

`communitypatchprojectcpp.htm` is advice, not a feature: "the **1.72 builder
resources** entry in the Map Exclusions page controls whether CPP's Builder
Resources are included". Following it meant looking for that entry — and it was
not there, because VB's whole **``PlayerExcludes``** table had never been ported.

It is a second exclude set, asked about once: ten starter/demo module names that
ship inside community packs, seven specific files, and two folders (builder
resources, script templates). Player adds them; Builder adds nothing. That is
the entire difference, and it decides what Create Installer leaves out — the
last thing anybody wants to discover after building thirty installers.

★ "mods" had to become an overridable exclude kind. The port could persist file
and folder exclusions but not module-name ones, and an exclusion that cannot be
persisted is one that comes back every launch. The additions go through
`add_exclude` rather than into the table directly, for the same reason.

Four of the five first-run questions are now asked: **which installation**,
**where the store goes**, **which group set**, **which edition** (at profile
creation), and now **player or builder**. The one left is the user-files folder
and its disable-detection setting, which is reachable from Settings and never
silent.

## Why 160 topics still say UNREVIEWED

Two reasons, and the second is the honest one.

**Mechanically**, `capability_sweep.py` counts a topic as reviewed only when its
file name appears as a row in this document. Bulk machine checking wrote no
rows, so the counter never moved. It tracks *verdicts written*, not *topics
checked*.

**Substantively**, the machine passes are not review, and saying "all three
sweeps are quiet" repeats the mistake this whole exercise exists to correct.
Measured against the two real gaps found in this session:

| | `useattributefilters.htm` | `firsttimeexecution.htm` |
|---|---|---|
| names a checkable command | no | no |
| describes a click | no | yes (as does nearly everything) |
| "the Tool will/automatically…" | no | no |
| content carried in screenshots | **3 images** | **12 images** |

Both would have scored quiet. The attribute filters were found by opening the
**screenshots** — the three tick boxes exist nowhere in the topic's text — and
the first-run flow by reading prose. So the sweeps prove three specific
negatives and nothing more:

* no unreviewed topic names a command without a handler;
* every *stated* interaction is wired;
* no "the Tool will…" sentence promises something absent.

★ **What they cannot see:** a capability that lives in a screenshot, a flow
described across several sentences with no imperative verb, and any difference
of *content* between a screen that exists here and the one it was ported from.
Reading is the only instrument for those, and reading is what found both gaps.

Reading the backlog is therefore still worth doing, and is being done in
batches, worst-first: topics ranked by how much of their content is in images.
The first batch found `statusicons.htm` — eleven icon meanings the original
shows in the Mod Properties and Details panels, where the port was printing a
title-cased enum name.

## Where the help-topic sweep has got to

160 topics remain UNREVIEWED, and that number is now misleading in a useful way.
Classifying them rather than reading them:

| | |
|---|---|
| 23 | procedures naming a command that is ported |
| 41 | short reference / navigation stubs |
| 24 | reference prose (glossary, FAQ, version history) |
| 48 | longer prose worth a skim |

Three machine passes over all of them found:

* **no unreviewed topic names a command that is missing** — only the five
  recorded as non-goals or decisions, plus `mshistory.htm`, which is the version
  history and mentions everything;
* every interaction they describe is wired, after the five closed above;
* no sentence of the form "the Tool can/will/automatically…" describes something
  the port does not do.

★ So the remaining topics are **documentation of ported behaviour**, and reading
them one by one is no longer the cheapest way to find a gap. The sweeps are: does
a topic name a command that has no handler; does it describe an interaction; does
it promise a behaviour. All three are quiet.

**Recorded as a decision, not a gap:** `newtopic53.htm` (Application Definitions
File) describes an online INI of hard-coded values, fetched at start-up and
cached by revision number. The only value in it this port needs is where the
download rules live, and `vault/rules_source.py` already fetches those from two
published hosts with a cache and a bundled floor. A general "fetch a file of
constants before the window opens" mechanism would add a network dependency at
launch for no capability we lack.

## Sweeping for sentences, not for commands

With the commands nearly all wired, the remaining risk was interactions with no
command id — the shape that found the profile-name click and the Properties
heading. Two machine passes over the 164 unreviewed topics:

1. **Which commands do they tell people to click?** Captions map back to ids, so
   this is checkable rather than readable. Result: **no unreviewed topic names a
   command that is missing** — only the five already recorded as non-goals or
   decisions, and `mshistory.htm`, which is the version history and mentions
   everything.
2. **Which sentences describe an interaction?** Pulling every "You can click…",
   "Right-click…", "Double-click…", "Hover…" out of the same topics gave about
   sixty, most already ported. Four were not:

   - Recent Mods: Pin / Unpin / Remove (`newtopic47`).
   - A mod's status icon installs or uninstalls it (`newtopic28`).
   - Right-click Activate brings the game's mod with it
     (`switchinggamesaves`, `restoregamesavesfrombackup`).
   - The Character Explorer's **Select** button (`mscharacterviewer`) — recorded
     as needing "a design decision on where it'd be invoked", which the help
     answers outright: it closes the Explorer on the mod the character belongs
     to.

★ Sweep the *sentences*, not the topics. A topic list tells you what to read; a
sentence list tells you what to check.

## Updating the tool: the half worth having

`bhnitdownload.htm` — VB downloads a 7-Zip from the Vault and unpacks it over
itself. The port asks the project's releases what the newest version is and, if
that is newer, offers the release page.

**Replacing a running application's own files is the part of a self-updater that
goes wrong**, and it goes wrong on the machine of whoever least wanted it to.
The useful half — *there is a new one, here it is* — needs none of it. Nothing is
sent either: it reads a public list, and does not report who asked or what they
have installed.

Version comparison is deliberately forgiving (`v1.2` vs `1.2.0`): a tag is
written by a person, and refusing to compare would fail exactly when the check
is most wanted. A 404 means no release has been published yet, which is not a
failure.

`MsResetWebMenu` in the same commit. VB re-fetches the favicon beside each Web
menu entry and validates the ones it could not get; this menu draws one generic
icon, so there is nothing to re-fetch and the validation is the whole of it.
★ A 403/405/429 does **not** count against a link — plenty of sites refuse HEAD
and answer GET perfectly well, and calling those broken sends someone off to fix
what is not wrong.

## Update Enhanced Edition Files — and a field nothing read

`ProfileData.original_ee_files` existed from the start, was saved and loaded
with the store, and **was read by nothing**. It is the table this command fills:
the per-profile record of what the Enhanced Edition ships *now*, on top of the
bundled snapshot.

Why it matters, measured on the owner's current install: of 280 shipped files,
**15 have changed and 99 are new** since the bundled table was captured. A file
whose CRC does not match its table entry is treated as one a mod changed, so
without this all 114 are invisible to *Create Original Restorers* — which is
precisely the "restorers quietly stop recognising half the game" that
`updatedeefiles.htm` exists to prevent.

★ All five shipped folders are in the **install** — `mod`/`mus`/`nwm`/`txpk`
under `data/`, and `ovr` beside it. That is the "Enhanced Edition Library
directory" the help names, and it is *not* where mods go. Assuming the user dir
made the first version of the test scan nothing at all.

★ A file the table knows and the scan does not is **not** reported as removed: a
folder that could not be read would otherwise look like the game had lost half
its files.

## One command deliberately not ported: Enable Closing

`newtopic42.htm` is a FAQ for a problem VB creates: while the game or the
toolset is running it **disables Exit and removes the window's close button**,
and *Enable Closing* on the Options menu is the way out when the game has since
died and the tool is stuck open.

The port does not disable closing, so there is nothing to re-enable. Porting the
pair faithfully would mean adding a way to strand someone in order to ship the
escape hatch for it — the FAQ exists because that happens. `MsEnableClosing`
therefore stays visible and disabled, like every other unported command, and
this is a decision rather than an omission.

## Validate Neverwinter Nights — where real data changed the design

The last of `validatedatabase.htm`'s five validations. It walks the game's own
folders for files with an extension the game does not read — the game-side twin
of *Remove Illegal Mod Files*, which asks the same question of a mod's payload.

★ VB shows the list and a **Delete Illegal Files** button that recycles the whole
of it. Run against the owner's real installation, the list was four files and
**every one was legitimate**: PRC's two `.hif` hakpak-information files, and the
`repository.json` the game itself writes into `mod` and `nwm`. Ported literally,
this feature's first use would have deleted four working files.

So the port shows tick boxes, all clear to begin with, and deletes what has been
ticked. "The game does not read this extension" is a fair thing to point out and
a poor thing to act on unasked. The fixture-based tests could never have shown
this — only running it against a real install did.

## A third wrong "Ported" — and a guard so there is no fourth

`newtopic73.htm` (*Show BioWare's Portrait Images*) was recorded ported against
`MsOriginalPortraits`. The menu item was there; nothing was wired to it. Same
mistake as `createcharrestorers.htm` and `newtopic55.htm`, three for three: a
**present control id read as a working feature**.

★ `tests/test_capability_status_claims.py` now reads this file, pulls every
command id off a line that says *Ported*, and fails if any of them has no
handler — or does not exist at all. The check is a few lines and it is the only
thing standing between this file and being confidently wrong. Verified against
a planted bad claim, not just against a clean file.

The feature itself: the game keeps its built-in portraits inside its own data
files, where nothing here can read them, so a character rolled with one shows no
picture. The Vault publishes them as a reference archive; ticking the option
fetches it on request — ~150 MB down, ~350 MB unpacked, which is why it is asked
for rather than assumed — and the folder joins `portrait_search_dirs()` **last**,
so a mod's replacement for a built-in portrait still wins.

## Dependencies: what the tool already knows and was throwing away

Owner, on the PRC-ified Drive modules: *"we can actually link them because we do
a vaultkeeper linkage when we search for their dependencies, so in theory you
could have a transient jump from the prc-ified module to the vault module to its
dependencies."* Correct, and half of it was already there:
`install_prc_module` records the Vault page it matched as the mod's `web_link`,
which is the hop that lets Auto follow that page to *its* prerequisites later.

The other half was being discarded. The requirements were **settled by the user
a few clicks earlier** — that is the one moment they are known for certain
rather than inferred — and each was installed as its own mod without anything
recording that it *was* a dependency. It is written down now, for the ones that
actually installed: a dependency on a mod that is not there would make every
later uninstall reason about something that does not exist.

`newtopic18.htm` also supplied two missing pieces of Auto: a progress dialog
with **Cancel** (a stopped run must not read like a run that found nothing —
hence `cancelled` in the result and "Stopped." in the message), and the
follow-up offer to turn on **Uninstall Mod Dependencies**. That last one matters
more than it looks: knowing a mod needs CEP does nothing on its own, and the
preference that acts on it is off by default, so VB asks about it exactly when
the answer has become useful.

## The `bh*` topics, checked rather than read

The 26 `bh*` topics are the button-help ones, so their file name *is* a control
id and they can be checked instead of read. 24 of 26 turned out ported; the
sweep's value was the two that were not.

★ Do the check with `implemented_commands()` and the **real** id, not a guessed
one. My first pass guessed `MsAliasSectionEditor`, `MsFolderMapping`,
`MsRunMenuEditor` — the actual ids are `MsAliasSection`, `RbnMapFiles` and a
Settings tab — and every guess came back a false NOT-FOUND. Same failure mode as
the false *Ported*, in the other direction.

**Backup and Export Manager** was the real gap: `MsBackupManager` sat in the
Tools menu doing nothing, and `databackups.htm` was recorded Ported on the
strength of Backup Data / Restore Data, which do work. The manager is the screen
`corruptedprofiledata.htm` sends people to. Now built: three tabs, because the
three are restored by three different routes; Restore offered only for a
profile-store backup, since an archive needs unpacking and that is what Restore
Data is for; Delete honours the recycle-bin preference. Exports now default to
the store's own *Exported Mods* folder so the third tab has something to list.

Still open from that sweep: `bhnitdownload.htm` (self-update).

## Fonts and colours — ported to the size of *this* application

VB keeps a font per UI element (11) and a colour per element (25). Copying that
list would mean 21 colour pickers wired to nothing, which is a preference that
lies to the person setting it — the "setting nothing reads" defect, built on
purpose. So the Appearance page offers what this application actually paints
with: one font family and size, the theme, and the **four semantic status
colours** (`theme._STATUS_COLOURS`) that mark a mod's state in the list.

A test ties the two lists together, so a fifth colour added to the painting code
without a picker fails.

★ Applying a font must always start from the font the app **launched** with, not
the one currently set. "Leave it alone" and "put it back" are indistinguishable
from the current font, so without that, a custom font could be chosen and never
undone until a restart — the setting would look broken. A leaked font family
between tests is what surfaced it.

An unset colour follows the theme, which keeps the light/dark pair that makes it
legible on either background; a set one is used exactly as given, because
adjusting the user's choice for contrast would make the picker a suggestion box.
Clearing has to stay reachable, so "unset" is stored as absence, never as
today's default value.

## Group sets — the third first-run question, now asked

`defaultgroupsets.htm` was one of the five first-run questions still unasked.
A new profile had **no groups at all**; VB seeds it from one of four sets.

It reads like a cosmetic preference and is not. `faqgroupnumbers.htm` explains
why: groups sort by name, that order is the order mod files are copied, and that
order is what settles a conflict between two mods. **Picking a set is picking a
conflict policy** — and it is the one first-run answer that is awkward to revisit,
because by then mods have been sorted into the groups it created.

That changed `worth_asking`: it used to be "more than one install *or* more than
one place for the store". The group set is always a real choice, so having found
an installation at all is now reason enough to ask.

★ Seeding only ever applies to a profile with **no** groups. Re-seeding one
someone has organised would put back every group they had deleted.

The remaining unasked first-run questions: which edition, where the user-files
folder is (+ the disable-detection setting), Player vs Mod Builder, and whether
to create Restorers.

## Auto-backup of game saves — a behaviour with no control at all

Not a command, not a dialog, not even a menu item: it happens *because you
opened the Game Saves Manager*. NWN keeps every mod's saves in one folder, so a
module that chains into its next chapter leaves two mods' saves side by side;
opening the manager moves all but the current mod's into a backup folder each,
so the live folder holds only the game in play.

Two things worth keeping:

- **Quick Saves and Auto Saves stay put**, whatever mod they belong to. The help
  says so outright, and it is the safer reading — the game is about to overwrite
  those slots anyway.
- The report has to be taken **after** the backup runs, or it describes a folder
  that has just moved.

★ The test asserts the *invariant* (the live folder ends up holding one mod's
standard saves) rather than naming which mod wins — "current" is the newest
save, so asserting a particular folder just re-implements `current_game_save`
in the test, and my first attempt got it wrong that way.

## Find: one command, three meanings

`findoperations.htm` says it outright — "the scope of the search operation
depends on which element in the UI has focus" — and that sentence is the whole
feature. Ours always opened the profile file-search, which made the other two
scopes unreachable from the menu they are documented under. A command diff
could not see this: `MsFind` was present and wired the whole time.

| Focus | Scope |
|---|---|
| the mod list | the whole profile (Find Files dialog) |
| contents / properties list | step through matching rows, both directions |
| the notes, or a file viewer | step through occurrences in the text |

★ Use `self.focusWidget()`, not `QApplication.focusWidget()` — the former
answers for the window whether or not it is the active one, which is both more
accurate and testable without a window manager.

## The recovery options — a third invisible capability

`commandline.htm` is the same shape as the first-run gap and the attribute
filters: no screen, no command id, nothing for a sweep anchored on ported
dialogs to catch. It is also the most consequential of the three, because every
option on it exists for one situation — **the app will not start** — and three
FAQ topics (`faqnitcrashes`, `corruptedprofiledata`, `corruptedsettings`) are
just pointers to it. Without it, a corrupted store is unrecoverable from inside
the app.

Five options, each abbreviable to its first letter, plus the start-up keys for
when there is no command line to type on (someone double-clicked an icon):

| Option | Key | What it does |
|---|---|---|
| `-CommandMenu` / `-C` | Ctrl | The menu of the other four |
| `-Settings` / `-S` | | Settings, before any profile data is read |
| `-ProfileValidate` / `-P` | | Validate the profile after it loads |
| `-RestoreProfileData` / `-R` | Alt | List the data backups before loading |
| `-MusicOff` / `-M` | Shift | No start-up sound |

★ **Ordering is the feature.** Settings and Restore must run *before* the
profile is read, because the read is what crashes. The test asserts the
sequence, not the calls.

Two things this turned up:

- We suppressed the start-up sound on **Ctrl**, which is VB's key for the
  options *menu*. Shift is the sound. Fixed.
- Restoring is deliberately in `vaultkeeper/recovery.py`, not on the
  controller: it must work on file names and bytes with no profile loaded.

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
| `MsGetUpdate` | Self-update — the *check* is built (`MsUpdateNow`); the in-place replace is deliberately not |
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

## A second verdict this file got wrong — and the Move-to trio

`newtopic55.htm` was recorded **Ported (`MsMoveToDev`)**. The command exists in
the menu; nothing was wired to it. Same failure as `createcharrestorers.htm`
below: a *present control id* was taken as evidence of a *working feature*.
`implemented_commands()` is the check that would have caught both, and it is
cheap — use it, not grep, before writing "Ported" against a command.

The three are one family, and `dealwithmodupdates.htm` needs two of them:

- **Move to Folder** — done. The mapper already knew each extension's second
  home (`.hak` → `patch`, `.tga` → `override`), so this toggles between them.
- **Move to History** — done. `_History` sits *beside* the payload, not inside
  it, so the old version is kept but stops being installed. That is exactly what
  "retain the old version of the file" has to mean.
- **Move to Development** — **still a gap**, and deliberately so: it needs the
  EE development-folder feature we do not have (a `development` folder in the
  mapper plus the preference that switches it on). VB gates it on EE edition
  **and** the preference **and** a mapped extension **and** (`.hak` or a
  primary/secondary of `override`). Worth doing with that feature, not before.

★ Both move commands uninstall an installed mod first, as VB does. The files are
about to live somewhere else; the copies already in the game would be orphaned
with nothing pointing at them.

★ `scan_mod_files` only ever **adds**. A move that does not also drop the old
FileKey leaves the file recorded in both places, and the mod goes on claiming to
install something that is not there.

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
