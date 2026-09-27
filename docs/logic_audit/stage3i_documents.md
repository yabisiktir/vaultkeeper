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
