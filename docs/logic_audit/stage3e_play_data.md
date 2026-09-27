# Stage 3e — play data and logs

Method: NIT's `PlayDataManager.ClientLog.GetTimes` / `LogDate`, `AddLoggedTimes`,
`RecordTime` compared line by line with `game/client_log.py`,
`game/play_data_manager.py` and the post-game handler.

| ID | Area | Finding | Verdict |
|---|---|---|---|
| E1 ✅ | missing haks | NIT shows "Module Load Failure" with the hak files the game could not load, and offers Copy to Clipboard. VK parsed the list and discarded it — the player never learned why a module failed. Now shown. | BUG → fixed |
| E2 ✅ | log markers | NIT matches `[`/`I [`, "Loading Module:", "Server Shutting Down" case-insensitively; VK did not. | BUG (minor) → fixed |
| E3 ✅ | minimum session | `ConfigMinPlayTime` 10 min (fixed in 3b, B3). | fixed |
| E4 | time attribution | per-module spans, shutdown handling, abnormal termination closed at stop time, 5-minute execution floor, path entries through the save-name map: same. VK de-duplicates the missing-hak list inside the parser (NIT does it in `AddLoggedTimes`): same result. | same |
| E5 | `RecordTime` | minimum, pending times for mods not in the profile (longest kept), play-time file, recorded games: same. NIT's shared-network sync (`SharedNit`) is not ported (VK uses export/import instead). | same / n/a |

Regression tests: `tests/test_play_log_parity.py` (both fail on the old code).
