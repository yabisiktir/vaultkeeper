# Phase 5 — Play loop (candidate #2)

Status: **domain layer complete and tested (headless).** The play-tracking loop —
GameMapper + PlayDataManager + GameSaves + client-log parsing + the RTF play-time
files — is ported from VB and fully unit-tested. UI dialogs, launch/exit driving, and
the real `module.ifo` decode are the remaining wiring (see "Not yet" below).

## Done

7 commits (records → GameSaves → GameMapper → client log → RTF → PlayDataManager):

- **core/play_time.py** — `PlayTimeInfo` (one play-time line; parses "150 hours 16
  mins" → TimeSpan, descending-date sort, CI equality) + `PlayData` (totals + per-mod
  durations). **core/formatting.py** — LazWorks `ToInteger` (−1 on non-numeric),
  `ToDateString` ("dd MMM yyyy"), `ToPlural` (day/ies/es/ices quirks).
- **game/game_saves.py** — `GameSaveInfo` (number prefix → quick/auto/standard,
  `.sav` name, `savenfo.txt` location) + `GameSaves` synchronous scanner (folders,
  counts, sizes, current-info/save/location, remove/add). Validated against the real
  `~/Documents/Neverwinter Nights/saves` (test skips if absent).
- **game/game_mapper.py** — the resolution ladder (`GameMapper.vb` + 6 partials).
  `log_name_to_mod_name`/`save_name_to_mod_name` walk installed keys → non-default
  installer conflict lists (installed mods only) → patch-file exclusion (`is_not_patch`
  + original-campaign patch sets) → user prompt → cross-profile `SaveNames` (built by
  scanning every profile's mod files) → profile picker → typed name. `UserResponses`
  memory, `create_map_entries` save-name mapping, rename propagation. **Injected seams:**
  `GameMapperPrompter` (choice/name/profile UI) and `ModuleInfoReader` (module save
  name/description). Persistence is native JSON.
- **game/client_log.py** — `parse_client_log` ports `ClientLog.GetTimes`: parses
  Diamond `nwclientlog1.txt` / EE `nwenginelog.txt` (`I [` prefix), attributes elapsed
  time between "Loading Module:" entries per mod, handles shutdown/abnormal
  termination, missing-hak collection, `< 5 min` → zero execution, backslash-path →
  save-name resolver vs logged-name resolver, year backfill from the session date.
- **core/rtf.py** — minimal RTF ↔ text: `write_rtf` (ANSI, `\uc1`, `\'xx`/`\uN`
  escapes) and `read_rtf_text` (skips font/colour/stylesheet/`\*` destinations,
  `\par`/`\tab`, uc-skip). Round-trips our own output and reads RichTextBox RTF.
- **game/play_data_manager.py** — `PlayDataManager.vb`: `apply_logged_times`,
  `add_time`/`reset_time`/`set_play_time`, `rename_mod`, `record_time` → RTF
  `.Game Play Time.rtf` write + read-back (`>38`-char/numeric-first line parse, 2+-space
  column split), `UpdateCompletedInfo` (DateCompleted/CompletedCount), pending times +
  `record_completed_games`, `validate` (vs game-save backups), `record_deleted_games`,
  `FormatTime`/`FormatDays`. Settings/`to_mod_key`/save/refresh injected.

Test count: **364 passed** (+87 this phase), ruff clean, py3.13 / PySide6 6.8.3.

## Not yet (wiring & one real decoder)

- **Real `ModuleInfoReader`** — the salvaged `core/formats/erf_reader.py` sources
  `save_name` from an *empty placeholder table*, so it can't feed GameMapper's scan on
  real data. Needs: locate the `module.ifo` resource in the ERF → GFF-parse its
  `Mod_Name` (save name) and `Mod_Description`. VB refs: `ErfFileReader.vb:160-221`
  (`ModDescription` from ERF localized strings, `ModSavName` from `IfoReader.GetFieldText
  ("Mod_Name")`). Validate against the user's real `.mod`/`.nwm` files. Scoped follow-up;
  the GameMapper ladder is fully functional via the installed-key path without it.
- **Qt prompter** — implement `GameMapperPrompter` with the choice dialog / name editor
  / profile picker; wire into the controller.
- **Launch/exit loop** — `TimedExecution` equivalent (Play/Toolset launch with mac
  strategies), then on exit: rescan saves, `parse_client_log` → `apply_logged_times`,
  auto restorers, save-count warning. Wire GameSaves title-bar info.
- **Viewers** — PlayDataViewer / ModPlayViewer / PlayDataViewPending / Game Saves
  Manager (archive/reduce/restore) / UserResponseEditor.
- **Deferred by design** — `SyncPlayTimes` (shared store, Phase 6), pre-5.0 `Migrate`,
  `DailyPlayTimeInfo` auto day-conversion factor, `FormatStartDate` (needs a LazWorks
  date-diff helper), crash-report handling, auto-loadscreen.

## Wiring notes for the consumer (controller)

`PlayDataManager` needs: a `PlayDataSettings` backed by the config store
(`play_time_mod`/`play_time`/`config_min_play_time`/`config_day_conversion_factor`),
`to_mod_key = game_mapper.save_name_to_mod_name`, `on_save_mods = controller.save`,
`on_contents_refreshed` = details-pane refresh. `GameMapper` needs a `GameMapperContext`
(profiles dir, active profile, data dir) + the real module reader + a Qt prompter.
