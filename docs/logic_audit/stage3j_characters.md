# Stage 3j — characters

Method: a differential run. NIT's own `BicFileReader.dll` (from the v8.0 build)
runs under Mono on this Mac, with no NIT form needed, and dumps every field its
`Info` reads; Vaultkeeper's reader (`nwnfile.formats.bic_reader`, in
nwn-save-editor) dumps the same fields; `stage3/bic_diff/compare.py` diffs them.
Corpus: 37 real characters (26 from `localvault`, 11 `player.bic` from save
folders), copied to a scratch folder first. Then NIT's `BicFileInfo.CharacterSummary`,
`CharacterFilter.IsValidLevelFilter`, `CharacterViewer.LbcFilter_Click` /
`ApplyClassFilter` and the portrait search order were compared line by line.

| ID | Area | Finding | Verdict |
|---|---|---|---|
| C1 | Fields | Name, gender, race, both alignment axes, classes and levels, experience, max hit points, gold, deity, portrait, six ability scores: identical on all 37, apart from C2. | same |
| C2 | Class level | NIT's reader reports `ClassLevel` 0 for one character whose file says 1 (the struct stores `ClassLevel` before `Class`). NIT hides it by showing any level below 1 as 1, so its display is right. | NIT artefact (VK reads the file correctly) |
| C3 ✅ | PortraitId | NIT reads `PortraitId` and, when the `Portrait` resref is blank, uses `po_` + that row of `PortraitNames.txt`. VK ignored it, so a character with a stock portrait stored that way showed none. Fixed in nwn-save-editor (`befd0c2`): the table is bundled; line N is row N, as LazWorks' `ToList` reads it (checked against the real library). None of the 37 used it. | BUG → fixed |
| C4 ✅ | Portrait search | NIT: ovr (EE), override, hak portraits, portraits, BioWare's. VK searched the portraits folder before the hak portraits. | BUG (minor) → fixed |
| C5 | Summary text | Title from alignment corners, total level, "Gender Race, Chaotic (n), Evil (n)", class lines, XP with the next-level countdown (same XP table), hit points, gold, deity, portrait, updated: same layout. VK adds subrace, current HP, and (in the detailed view) age, AC, BAB, saves and biography, and names PRC/community races and classes NIT shows as "Race 159" / "Class 57". | same / VK-better |
| C6 | Show stats | NIT hides the ability block unless `ConfigShowCharStats`; VK's Character Explorer always shows it. | DELIBERATE |
| C7 | Level/class filter | Validation messages, `<1` treated as `=1`, ranges, "level and higher" default, up to three classes matched as substrings of the summary: same. | same |
| C8 | `FilterSkillsByRank` | Default differs (NIT on, VK off); triaged in 3b (B11) as a viewing default. | DELIBERATE |

Regression tests: nwn-save-editor `tests/test_bic_portrait_id.py` (C3) and
`tests/test_character_viewer.py::test_hak_portraits_outrank_the_portraits_folder`
(C4).
