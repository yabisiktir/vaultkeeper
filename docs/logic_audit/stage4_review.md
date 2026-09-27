# Stage 4 — residual code review

Stages 1–3 ran NIT's own code (or compared it line by line) feature by feature.
Stage 4 covers what they could not: every member of the original that no stage
executed. Exit criterion (README): every residual row has a verdict backed by a
VB-vs-Python branch comparison, not a note.

## Method

`stage4/triage.py` puts each of the ledger's 3,284 members
(`../parity_audit/ledger_members.csv`) in one bucket:

| Bucket | Rows | Meaning |
|---|---|---|
| covered | 1,074 | its file was executed or compared line by line in a stage (`STAGE_FILES`) |
| no-logic | 1,134 | a *form* member whose body touches nothing a user keeps: no profile data, files, settings writes, mapper, processes or network |
| trivial | 162 | a data/logic-class member of three lines or fewer |
| n/a | 188 | ledger N/A (enums, plain properties, designer members) |
| **review** | **726** | everything else, reviewed by hand, core files first |

Members of data and logic classes are never "no-logic": a pure computation such
as `ModData.SetModState` changes nothing on disk yet decides what every mod shows.
The body extractor stops at the next member, so an auto-property does not swallow
the code after it (checked by sampling the largest bodies of each bucket).

Verdicts go in `stage4/verdicts.csv` (`same`, `fixed`, `deliberate`, `NIT
artefact`, `n/a`); `triage.py` then lists what is left in `stage4/residual.csv`.

## Batches

| # | Files | Rows | State |
|---|---|---|---|
| 1 | ModData.vb | 31 | ✅ |
| 2 | ProfileData.vb, ProfileData.Properties.vb, GroupMemberData.vb | 107 | |
| 3 | Paths.vb, ProfileInfo.vb, ProfileInfoManager.vb, NwnFolderInfo.vb | 113 | |
| 4 | HakPatchManager.vb, ErfFileReader.vb, InstallationAnalyser.vb, DependencyManager.vb | 41 | |
| 5 | NIT.Menu.vb, NIT.Common.vb, NIT.Workers.vb, NIT.ModView.vb, NIT.* views | ~160 | |
| 6 | Defs.vb, Settings.* | ~70 | |
| 7 | the rest (viewers, GameManager, ModExplorer, …); NetworkManager.vb as one verdict (not ported) | ~200 | |

## Batch 1 — ModData.vb

31 rows: 26 same, 5 fixed.

| Member | Finding | Verdict |
|---|---|---|
| `ValidateInstallerType` | NIT runs it for every mod with an installer on each profile load: duplicate file entries dropped; the identifier made to match what the mod is (`.nitins` with source files, `.nitres` without), renaming the installed copy too; a missing one created. VK never did: a restorer given source files (Add Files) stayed a restorer and Create Installer refused to build it. Ported as `validate_installer_types` (profile load and Validate Mods). Real-data dry run (read only): 11 mods checked, one gains its missing `.nitins`, nothing renamed. | MISSING → fixed |
| `CreateTypeFile` | `_create_identifier` wrote the new identifier and left the opposite one, so a mod could carry both (`update_installer` on a restorer). It now removes the other. | BUG → fixed |
| `Remove` | Deleting a mod recycles its notes in NIT; VK left them until Validate Mods. | fixed |
| `Rename` | Notes follow the mod (3i N1). | fixed earlier |
| `SetModState` | Same branch for branch (including NIT comparing the override count with the whole profile's file count); the `nwnpatch.ini` name test now ignores case, as `Option Compare Text` does. | fixed (minor) |

Regression tests: `tests/test_installer_type_parity.py`,
`tests/test_notes_parity.py::test_deleting_a_mod_recycles_its_notes`.
