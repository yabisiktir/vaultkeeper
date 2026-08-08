# Dialog parity sweep — help topics vs the ported screens

A pass over every ported dialog that has a help topic (24 topics, 26 references),
checking the documented and Designer-declared controls against what the port
actually offers. Run `scan_captions.py` to regenerate the candidate list; each
entry below was then confirmed by hand against the VB form's own handlers,
because the scan cannot tell a missing control from a renamed one, and Designer
files are full of placeholder captions (`ToolStrip1`, `Long Sword`, `Cave`).

The method is the one that found the earlier gaps: read `<Form>.Designer.vb` for
the control set and `<Form>.vb` for the handlers, not the ledger's status.

## Fixed in this pass

| Screen | What was missing |
|---|---|
| **Character Explorer** | The list showed the character name, not the `.bic` file name — 36 files under 3 names read as identical rows (VB's column is titled *Files*). Fixed, with the name/mod/path on the tooltip. |
| **Character Explorer** | *Only show Ranked Skills* (`CbRanked` → `Defs.GetFilteredSkills`), remembered in settings as VB remembers `FilterSkillsByRank`. A PRC character has ~40 skills and ranks in a handful. |
| **Character Explorer** | Clicking the portrait opens the Portrait Manager (`PicPortrait_Click` / `CmOpenPortraitManager`). |
| **Character Explorer** | Escape clears the name search, as the help topic states. |

## Built since (items 1–4 of the original list)

| Screen | What landed |
|---|---|
| **Mod Explorer** | The mod-state comparison — *matching* / *more files installed than* / *less files installed than* (`TsStateEqual`/`Greater`/`Less`). Stated positively; VB writes it as an exclusion. The only way to ask "what is half-installed?" |
| **Game Saves Manager** | *Character Summary* (opens the character in the selected save) and *Open Folder* (`CmCharacterSummary` / `CmOpen`). |
| **Installation Analyser** | *Open Folder* and *Properties* on a file row; the browser report now carries each file's real path. |
| **Download Project** | *Copy File Name* and *Copy Direct File Link*, the latter enabled only when the file has one. |

## Built since (the rest of the list)

| Screen | What landed |
|---|---|
| **Mod Explorer** | The Weapon / Start / End / Hench columns, with VB's numeric filters (`>`, `=`, `<`, bare number meaning "greater than") and a weapon text filter. |
| **Installation Manager** | Sort the set list by Name / Created / Updated, ascending or descending. *Current* stays pinned at the top — it is the live state, not a snapshot. |
| **Start Screen Manager** | *Repair Prefixed Image Exclusions* — excludes every prefixed image that is not excluded, which cannot be spotted by eye in a folder of hundreds. |

## Built after the owner's decisions (all three: be faithful)

| Screen | What landed |
|---|---|
| **Mod Explorer** | The group filter now persists (VB `GroupNameFilters.txt`, written on close) with *Undo Group Changes* reverting to the saved set. |
| **Mod Explorer** | Name-prefix filters and *Undo Prefix Changes* — add/edit/remove prefixes in the Filters dialog; unticking one hides every mod whose name starts with it. |
| **Installation Manager** | The Group Selector pane (`LvGroupSelector`): tick a group to add it to the set whole, untick to remove. User sets only. |

**Two things I had recorded wrongly, corrected by reading the VB:**

* *Undo Group Changes* is **not** an undo stack over group moves. It re-reads the
  group-filter tick-boxes from their file, discarding unsaved changes.
* A **prefix is not a field on a mod.** `ModData` has no prefix in VB either — a
  prefix is just user-entered text matched with `StartsWith` against the mod
  name. I had scoped this as "a domain change touching the store format", and it
  needed no domain change at all.

Nothing from the original sweep is now outstanding.

## Checked and found already faithful

Character Explorer's summary (abilities, age, AC, BAB, saving throws — VB passes
`showStats:=True` at `CharacterViewer.vb:1242`, and so do we, plus a Biography
the original does not show); the level/class filter (measured 36 → 16 → 0 on the
owner's store); Character Filter's *Clear all marked classes*; Doc Organiser's
Version / Rename To / Reset; Mod Play Viewer's end-level filter.

## Known non-goals, restated so they stop resurfacing

* **Shared NIT Store** — `NetworkManager.vb`'s live sync. Its whole payload is
  two file types; mod export/import is ported instead, as a file you can move.
* **Doc Organiser *Next*** — VB processes one mod at a time and steps through a
  queue; the port shows every selected mod at once, so there is nothing to step.
* **Start Screen *Import* / *Clear Exported*** — both gated in VB on a shared
  store.
* **Mod Explorer notes and prefix filters** — `ModData` has no notes field and
  the port has no mod-name prefix feature. These need a domain change first, not
  a widget.
