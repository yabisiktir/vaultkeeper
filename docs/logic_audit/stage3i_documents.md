# Stage 3i — documents (Documentation Organiser)

Method: NIT's `DocOrganiser.vb` (`BtCopy`, `BtNext`, `CmVersion`, `CmRename`,
`CmRenameTo`, `CmReset`, `TsUncheck`), `DocOrganiser.DocInfo.vb` (qualifier,
`DocName`, `RemoveVersionText`), `DocOrganiser.ProcessDocs.vb` (scan, extract loop,
CRC match, unique numbering) and `NIT.Common.IsRunDocOrganiser` with its callers
(`MsDownloadProject`, `MsUpdateDownloads`) were compared with
`game/documentation.py`, the controller and `ui/dialogs/doc_organiser.py`.

| ID | Area | Finding | Verdict |
|---|---|---|---|
| D1 ✅ | After downloading | NIT asks "Do you want to run the Documentation Organiser?" after Download Project and Update Downloads, with "Always take this action." ticked (`ConfigRunDocOrganiser`). VK never offered it. Ported (`run_doc_organiser`). VK skips the question when there is nothing to copy; NIT asks and then closes the empty organiser. | MISSING → ported; VK-better detail |
| D2 ✅ | Archives in archives | NIT extracts archives found inside archives and qualifies each doc by the archive it came from. VK read only the outer archive's index, so a readme inside a `.zip` inside a `.7z` was never listed (or copyable). Such archives are now unpacked and recursed; Copy extracts the inner archive to find the doc. | BUG → fixed |
| D3 ✅ | Version toggle | Docs described from an archive index lost their versionless qualifier, which decides whether the Version toggle is offered. | BUG (minor) → fixed |
| D4 | Naming | Qualifier (mod name for loose files, archive name for extracted ones), title-casing, version stripping, "already starts with the qualifier": same. VK guards NIT's crash on a qualifier that is only a version word. | same / VK-better |
| D5 | CRC match, numbering | A download matching a Contents doc by CRC is unticked and linked both ways; duplicate names get " 1", " 2": same (case-insensitive, as NIT's `Option Compare Text`). | same |
| D6 | Copy | Into the mod root, overwriting, per checked row: same. | same |
| D7 | Several mods | NIT steps through mods with Next; VK shows all selected mods in one view. | DELIBERATE (UI) |
| D8 | Speed | VK describes archive docs from the 7-Zip index (path, size, CRC) instead of extracting; archives are unpacked only when they cannot be listed or hold archives. | VK-better |

Regression tests: `tests/test_doc_organiser_parity.py` (D2 tests fail on the old
code) and `tests/test_doc_organiser.py`.

## Mod notes

Method: NIT's `ModData.Notes` / `Rename`, `NIT.ModView` notes display,
`ProfileData.ValidateNotes`, `ProcessNotesSaved` and `CreateMissingNotes` against
the controller's `mod_notes_path` / `read_notes` / `save_notes` / `validate_notes`
and the main window's notes pane.

| ID | Area | Finding | Verdict |
|---|---|---|---|
| N1 ✅ | Rename | NIT renames the notes file with the mod. VK did not (single or bulk rename), so the notes were orphaned, and N2 then deleted them. Both renames now take the notes along; open, edited notes are saved first. | BUG (data loss) → fixed |
| N2 ✅ | Orphaned notes | NIT sends them to the recycle bin; VK used `unlink`. | BUG → fixed |
| N3 | Saving | Saved only when edited, with the confirm-saves question; remembered position per mod. | same |
| N4 | Formatting | NIT's notes pane is a rich-text editor. VK reads the RTF as plain text and writes plain RTF, so *editing* a note NIT formatted (bold, colour, fonts) drops the formatting; merely viewing it does not. | GAP, flagged for the owner (needs a rich-text editor) |
| N5 | Empty notes | NIT creates an empty notes file for every mod (`CreateMissingNotes`, and on display); VK writes one only when there is text and deletes it when cleared. | DELIBERATE |
| N6 | Sync | `BehaviourSyncNotes` syncs through NIT's shared network profile (`SharedNit`), which VK does not port (export/import instead). | n/a |

Regression tests: `tests/test_notes_parity.py` (the three controller tests fail on the old code).
