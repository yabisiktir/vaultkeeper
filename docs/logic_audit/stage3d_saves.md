# Stage 3d — game saves

Method: NIT's `GameMapper` (save / log name → mod), `GameManager` (Reduce,
Finished, Restore) and the post-game checks in `NIT.Workers.vb`, compared
branch by branch with `game/game_mapper.py`, `game/save_archive.py`, the Game
Saves Manager dialog and `MainWindow._on_game_exited`; scenario tests for each
difference.

| ID | Area | Finding | Verdict |
|---|---|---|---|
| G1 ✅ | save → mod mapping | NIT's `SaveNames`, `SaveNameMap`, the rules' `SaveNameRules` and the remembered answers are all **case-insensitive**; VK's were case-sensitive, so a save whose module name differed from the scan or a rule only in case went unmatched and the user was asked which mod it was. Now `CIStrDict`. | BUG → fixed |
| G2 ✅ | Reduce | NIT keeps `ConfigSavesRetention` saves (default 50), remembered; VK started at 100 every time. `saves_retention`. | BUG → fixed |
| G3 ✅ | after play | NIT warns when there are more than `ConfigSavesThreshold` (700) saves and recommends Reduce; VK said nothing. `saves_threshold` + `saves_count`. | BUG → fixed |
| G4 | Reduce algorithm | which saves are archived (keep the newest N, leading quick/auto saves stay), range naming: same. NIT asks when a range was already archived; VK merges into it (nothing lost; documented as bounded). | same / UI |
| G5 | resolution ladder | active profile → non-patch → single name → remembered profile → ask: same order and prompts. | same |
| G6 | deleting saves | NIT `FileRecycleBinForGames` (recycle bin) = VK `recycle_game_saves` (True). | same |

Regression tests: `tests/test_game_saves_parity.py`,
`tests/test_game_mapper.py::…ignore_case` (all 4 fail on the old code).
