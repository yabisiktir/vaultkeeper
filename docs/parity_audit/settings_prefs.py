#!/usr/bin/env python3
"""Finding-3 settings sub-sweep: classify every real VB user preference vs the port.

The VB app exposes ~80 `My.Settings.(Behaviour|Config|File)*` user preferences; the
port's settings model (config/settings.py) holds ~10. This encodes the first-pass
classification of each (orchestrator judgement, grounded in the port's known model
+ features). Statuses:
  PORTED      port has the setting or its behaviour (may be a different name)
  DIVERGENCE  cross-platform / Windows-shell / cosmetic — not applicable
  PERF        internal performance/threshold tuning — low value, N/A by default
  MISSING     genuine user-facing pref whose behaviour the port DOES implement but
              exposes no toggle  -> safe to add (a real setting)
  N/A         belongs to a NIT feature that is a non-goal here (shared store, NTFS)
  DEFERRED    genuine pref whose BEHAVIOUR is not ported -> a feature, not a toggle
              (do NOT add a hollow setting)

Emits settings_prefs.csv + a summary. NOT merged into seeds.json (those are method/
control keyed; these are setting keys — a separate ledger for finding 3).
"""
import csv
from collections import Counter
from pathlib import Path

AUDIT = Path(__file__).resolve().parent

CLASSIFY: dict[str, tuple[str, str]] = {
    # --- PORTED (setting or behaviour present) ---
    "BehaviourConvertBik": ("PORTED", "convert_bik_files"),
    "BehaviourInstallerInstall": ("PORTED", "install_after_create"),
    "BehaviourNumberRecentMods": ("PORTED", "number_recent_mods"),
    "ConfigMaxRecentMods": ("PORTED", "max_recent_mods"),
    "BehaviourWindows": ("PORTED", "remember_window_position"),
    "BehaviourRestoreDetailsPosition": ("PORTED", "remember_window_position (geometry)"),
    "BehaviourRestoreNotesPosition": ("PORTED", "remember_window_position (geometry)"),
    "FileRecycleBin": ("PORTED", "recycle_on_delete"),
    "BehaviourPlayStartup": ("PORTED", "startup_sound"),
    "ConfigToolbar": ("PORTED", "MsShowToolbar toggle"),
    "ConfigSettingsStartPage": ("PORTED", "SettingsDialog start_tab"),
    "BehaviourCloseSettings": ("PORTED", "dialog closes on save"),
    # --- DIVERGENCE (cross-platform / shell / cosmetic) ---
    "ConfigSplitterWidth": ("DIVERGENCE", "Qt splitters, not a stored width"),
    "ConfigPropertiesPanelAdjust": ("DIVERGENCE", "Qt splitter"),
    "BehaviourPropertiesPanel": ("DIVERGENCE", "Qt splitter"),
    "ConfigSystemTrayMinimise": ("DIVERGENCE", "Windows system tray"),
    "ConfigShowDotNet": ("DIVERGENCE", ".NET version display, N/A"),
    "ConfigKeyDelay": ("DIVERGENCE", "Windows keyboard timing"),
    "ConfigRestartDelay": ("DIVERGENCE", "Windows restart timing"),
    "BehaviourScreenTip": ("DIVERGENCE", "Qt tooltips automatic"),
    "BehaviourScreenTipChar": ("DIVERGENCE", "Qt tooltips automatic"),
    "BehaviourPropertiesToolTip": ("DIVERGENCE", "Qt tooltips automatic"),
    "BehaviourToolTipText": ("DIVERGENCE", "Qt tooltips automatic"),
    "ConfigProgressPreferences": ("DIVERGENCE", "port builds synchronously"),
    "ConfigLinkProgress": ("DIVERGENCE", "progress-dialog preference"),
    "ConfigCancelMode": ("DIVERGENCE", "WinForms cancel semantics"),
    "ConfigRecentModsCursor": ("DIVERGENCE", "cursor state"),
    "ConfigShowCharStats": ("DIVERGENCE", "CharacterViewer already shows stats"),
    # --- PERF (internal tuning — N/A by default) ---
    "ConfigMaxCrcThreads": ("PERF", "CRC thread count"),
    "ConfigMaxIoThreads": ("PERF", "IO thread count"),
    "ConfigMaxLinkThreads": ("PERF", "download link threads"),
    "ConfigMaxRtfTasks": ("PERF", "RTF task count"),
    "ConfigWizardFileThreshold": ("PERF", "wizard file-count threshold"),
    "ConfigSavesThreshold": ("PERF", "saves count threshold"),
    "ConfigMinPlayTime": ("PERF", "min play time to record"),
    "ConfigAutoDayConversionFactor": ("PERF", "play-time day factor"),
    "ConfigDayConversionFactor": ("PERF", "play-time day factor"),
    "ConfigKeyDelayed": ("PERF", "timing"),
    # --- MISSING (behaviour ported, no toggle) -> safe to add ---
    "ConfigDefaultGroup": ("MISSING", "new mods go to GROUP_NONE; no default-group setting"),
    "BehaviourUninstallDependencies": ("MISSING", "dep graph + uninstall exist; no cascade toggle"),
    "BehaviourConfirmActions": ("MISSING", "port confirms some actions; no toggle"),
    "BehaviourConfirmSaves": ("MISSING", "no save-confirm toggle"),
    "ConfigDeleteLetoLogs": ("MISSING", "remove_leto_log_files command exists; no auto toggle"),
    "ConfigDisplayTgaImages": ("MISSING", "ImageViewer shows TGA; no toggle"),
    "ConfigDisplayStdImages": ("MISSING", "ImageViewer shows std images; no toggle"),
    "BehaviourDisplayImageFiles": ("MISSING", "DisplayInfo shows images; no toggle"),
    "ConfigPortraitDisplaySize": ("MISSING", "PortraitManager shows 5 sizes; no default-size pref"),
    "BehaviourMoveAddedMods": ("MISSING", "add-mods exists; no move-to-group-on-add toggle"),
    # --- DEFERRED (behaviour not ported -> feature, not a hollow toggle) ---
    "BehaviourAutoCharacter": ("DEFERRED", "auto character restorer (restorer subsystem)"),
    "ConfigCharacterRestorerPrefix": ("DEFERRED", "restorer subsystem"),
    "ConfigAutoLoadscreen": ("DEFERRED", "auto loadscreen install"),
    "BehaviourWorkshop": ("DEFERRED", "workshop enable/refresh partly deferred"),
    "BehaviourSelectGameMod": ("DEFERRED", "select-game-mod on play"),
    "BehaviourGamesManagerClose": ("DEFERRED", "game manager close behaviour"),
    "ConfigGameManagerEnabled": ("DEFERRED", "game manager enable"),
    "BehaviourInstallerRestore": ("DEFERRED", "installer restore-on-create"),
    "ConfigCopyOnPlay": ("DEFERRED", "copy config on play (play-loop pref)"),
    "ConfigCopyDebugModeOnPlay": ("DEFERRED", "debug mode on play"),
    "ConfigRunCreateInstaller": ("DEFERRED", "auto-run create installer"),
    "ConfigRunDocOrganiser": ("DEFERRED", "auto-run doc organiser"),
    "ConfigSlideShowContinuous": ("DEFERRED", "start-screen slideshow"),
    "ConfigSlideShowInterval": ("DEFERRED", "start-screen slideshow"),
    "ConfigSaveScreenCrop": ("DEFERRED", "start-screen crop"),
    "ConfigScreenInfoFromFile": ("DEFERRED", "start-screen info source"),
    "ConfigSavesRetention": ("DEFERRED", "game-saves retention policy"),
    "ConfigUseLocalRules": ("DEFERRED", "local download rules toggle"),
    "ConfigImportAction": ("DEFERRED", "legacy import action pref"),
    "ConfigDoubleClickAction": ("DEFERRED", "mod double-click action choice"),
    "ConfigDevelopmentFolder": ("DEFERRED", "dev folder mapping (Settings map editor)"),
    "BehaviourRetainProperties": ("DEFERRED", "retain props on rename/move"),
    "BehaviourSyncProperties": ("DEFERRED", "sync props across shared store"),
    "BehaviourSyncNotes": ("DEFERRED", "sync notes across shared store"),
    "BehaviourRestoreSelections": ("DEFERRED", "restore selection on load"),
    "BehaviourSelectHistory": ("DEFERRED", "selection history"),
    "BehaviourSelectPlayTimeFile": ("DEFERRED", "prompt for play-time file"),
    "BehaviourSelectTextFile": ("DEFERRED", "prompt for text file"),
    "FileCompressModFolder": ("DEFERRED", "compress mod folder on op"),
    "FileOverwrite": ("DEFERRED", "overwrite-without-prompt policy"),
    "FileRecycleBinForGames": ("DEFERRED", "per-category recycle (games)"),
    "FileRecycleBinForInstallers": ("DEFERRED", "per-category recycle (installers)"),
    "ConfigPropertiesPanelHeight": ("DEFERRED", "MsPropertiesHeight (divergence)"),
}

# Re-verified 2026-10-01 against the source (docs/parity_audit/DASHBOARD.md, Audit status):
# the first pass's DEFERRED / MISSING rows were mostly built since, and BehaviourScreenTip*
# had been filed as text tooltips when they are save-screenshot tips.
RECHECK_2026_10: dict[str, tuple[str, str]] = {
    "BehaviourAutoCharacter": ("PORTED", "auto_character (re-verified 2026-10-01)"),
    "BehaviourConfirmActions": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "BehaviourConfirmSaves": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "BehaviourDisplayImageFiles": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "BehaviourGamesManagerClose": (
        "DIVERGENCE",
        "NIT's 'Close the Game Saves Manager' tick on the after-play uninstall prompt; "
        "VK's Finished flow runs inside the Game Saves Manager"
    ),
    "BehaviourInstallerRestore": ("PORTED", "installer_restore"),
    "BehaviourMoveAddedMods": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "BehaviourPropertiesToolTip": (
        "DIVERGENCE",
        "hover help on the Properties heading; VK uses Help buttons"
    ),
    "BehaviourRestoreSelections": (
        "PORTED",
        "always on: mods reselected per profile (LoadSelections), Contents per mod; no "
        "toggle"
    ),
    "BehaviourRetainProperties": ("PORTED", "retain_properties_on_import"),
    "BehaviourScreenTip": (
        "MISSING",
        "hover Manage your Game Saves shows the latest save's screen.tga; VK has no such "
        "hover (only the Save Game Editor shows screenshots) (reclassified 2026-10-01: "
        "this is an image tip, not a text tooltip)"
    ),
    "BehaviourScreenTipChar": (
        "MISSING",
        "hover the Character Summary text shows the save's screen.tga; see "
        "BehaviourScreenTip"
    ),
    "BehaviourSelectGameMod": ("PORTED", "select_game_mod"),
    "BehaviourSelectHistory": ("PORTED", "selection_preference = history"),
    "BehaviourSelectPlayTimeFile": ("PORTED", "selection_preference = play_time"),
    "BehaviourSelectTextFile": ("PORTED", "selection_preference = text_file"),
    "BehaviourSyncNotes": ("N/A", "shared NIT store (non-goal)"),
    "BehaviourSyncProperties": ("N/A", "shared NIT store (non-goal)"),
    "BehaviourToolTipText": ("DIVERGENCE", "one tooltip style from the theme"),
    "BehaviourUninstallDependencies": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "BehaviourWorkshop": ("PORTED", "manage_steam_workshop + workshop_content_dir"),
    "ConfigAutoLoadscreen": ("PORTED", "auto_loadscreen"),
    "ConfigCharacterRestorerPrefix": ("PORTED", "character_restorer_prefix"),
    "ConfigCopyDebugModeOnPlay": ("PORTED", "copy_debug_mode_on_play"),
    "ConfigCopyOnPlay": ("PORTED", "copy_mod_name_on_play"),
    "ConfigDefaultGroup": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "ConfigDeleteLetoLogs": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "ConfigDevelopmentFolder": ("PORTED", "enable_development_folder"),
    "ConfigDisplayStdImages": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "ConfigDisplayTgaImages": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "ConfigDoubleClickAction": (
        "MISSING",
        "NIT offers Install or Uninstall (default) / Open Mod Folder / Ignore Double "
        "Clicks; VK always installs or uninstalls"
    ),
    "ConfigGameManagerEnabled": (
        "DIVERGENCE",
        "first-use explanation before the Game Saves Manager; VK opens it directly"
    ),
    "ConfigImportAction": ("N/A", "shared NIT store import (non-goal)"),
    "ConfigPortraitDisplaySize": ("PORTED", "setting added 2026-07 (FINDING_3_SETTINGS.md)"),
    "ConfigPropertiesPanelHeight": ("PORTED", "auto_properties_height (MsPropertiesHeight)"),
    "ConfigRunCreateInstaller": ("PORTED", "run_create_installer"),
    "ConfigRunDocOrganiser": ("PORTED", "run_doc_organiser"),
    "ConfigSaveScreenCrop": (
        "MISSING",
        "crop for the save screenshot tips; see BehaviourScreenTip"
    ),
    "ConfigSavesRetention": ("PORTED", "saves_retention"),
    "ConfigScreenInfoFromFile": (
        "PERF",
        "re-read start-screen info each time; VK reads it when needed"
    ),
    "ConfigSlideShowContinuous": ("PORTED", "slideshow_continuous"),
    "ConfigSlideShowInterval": ("PORTED", "slideshow_interval"),
    "ConfigUseLocalRules": (
        "N/A",
        "NIT testing switch ('Please do not change this setting'); VK has "
        "vault_rules_online"
    ),
    "FileCompressModFolder": ("N/A", "Windows NTFS compression"),
    "FileOverwrite": (
        "PORTED",
        "status-bar Overwrite toggle (logic audit 3f F3; default deliberately on)"
    ),
    "FileRecycleBinForGames": ("PORTED", "recycle_game_saves"),
    "FileRecycleBinForInstallers": (
        "DIVERGENCE",
        "VK always recycles replaced installers (logic audit 3b B9: safer)"
    ),
}
CLASSIFY.update(RECHECK_2026_10)

rows = [{"key": k, "status": s, "note": n} for k, (s, n) in sorted(CLASSIFY.items())]
with (AUDIT / "settings_prefs.csv").open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["key", "status", "note"])
    w.writeheader()
    w.writerows(rows)

c = Counter(r["status"] for r in rows)
print(f"classified {len(rows)} VB preferences:")
for s, n in c.most_common():
    print(f"  {s:11s} {n}")
print("\nMISSING (open gaps, see DASHBOARD.md):")
for r in rows:
    if r["status"] == "MISSING":
        print(f"  {r['key']:32s} {r['note']}")
