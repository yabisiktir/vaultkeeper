# Finding 3 — Settings depth (content gap)

The owner observed the port's Settings screen is "a few checkboxes" vs. the VB
app's far richer Settings. Investigation confirmed a **real content gap**, not
just form-factor: VB exposes **81** real `My.Settings.(Behaviour|Config|File)*`
user preferences; the port's `config/settings.py` modelled ~10.

Full classification: `settings_prefs.csv` (regenerate with `python settings_prefs.py`).

| Bucket | Count | Meaning |
|---|---|---|
| PORTED | 12 | setting or behaviour already present (maybe renamed) |
| DIVERGENCE | 16 | cross-platform / Windows-shell / cosmetic — N/A on macOS+Qt |
| PERF | 10 | internal thread/threshold tuning — low value, N/A by default |
| DEFERRED | 33 | genuine pref whose **behaviour is not ported** — a *feature*, not a toggle. Adding a hollow setting would be inventing UI, so these are tracked as deferred features, not settings gaps. |
| **MISSING** | **10** | genuine user pref whose behaviour the port **does** implement but exposes no toggle → safe to add a real setting. |

So "way more content" resolves to: a rich VB ListView form-factor + **33 deferred
features** (tracked in the handoff) + **10 real missing settings**. The perceived
shallowness is mostly the 33 deferred features surfacing as absent settings.

## Built (behaviour-wired settings on the Settings Behaviour tab)

All wired to real behaviour + tested (`tests/test_default_group.py`,
`tests/test_behaviour_settings.py`):

- **`ConfigDefaultGroup`** → `Settings.default_group` — new mods land in the chosen
  group (`controller.create_mod`); empty = ungrouped.
- **`BehaviourMoveAddedMods`** → `Settings.move_added_mods` — mods added from files
  move into the default group (`controller.add_mods_from_files`).
- **`BehaviourConfirmActions`** → `Settings.confirm_actions` — gates the destructive
  confirmation dialogs (`MainWindow._confirm`, used by remove/delete-file).
- **`BehaviourUninstallDependencies`** → `Settings.uninstall_dependencies` — uninstall
  cascades to dependency mods no other installed mod needs
  (`controller._with_removable_dependencies`).
- **`BehaviourDisplayImageFiles`** / **`ConfigDisplayTgaImages`** /
  **`ConfigDisplayStdImages`** → `Settings.display_image_files` — one toggle; when off,
  Display Info opens images as text (`MainWindow._on_display_contents_info`).
- **`ConfigDeleteLetoLogs`** → `Settings.delete_leto_logs` (default on) — a global
  Leto-log sweep (`controller.remove_all_leto_log_files`: every managed mod's installer
  + each installed game folder, VB `Workers.RemoveLetoLogFiles`) auto-runs on startup
  (`ui/app.py`, VB `DeleteLetoLogs` from the Shown event). The manual **Remove Leto Log
  Files** command runs the same sweep and is hidden while auto-delete is on
  (`MainWindow._apply_leto_menu_visibility`, VB `MsRemoveLetoLogFiles.Visible = Not
  ConfigDeleteLetoLogs`).
- **`BehaviourConfirmSaves`** → `Settings.confirm_saves` (default on) — prompts before
  saving edited Mod Notes when navigating away; off = silent auto-save
  (`MainWindow._save_current_notes`, VB `RttDetails.SaveChangesPrompt`). The port's one
  editable details surface (Mod Notes) is the faithful analogue of VB's rich-text
  details editor.
- **`ConfigPortraitDisplaySize`** → `Settings.portrait_display_size` (default `"Huge"`;
  Huge/Large/Medium per VB `Defs.PicSizes` H/L/M) — sizes the Character Explorer portrait
  preview (`ui/dialogs/character_viewer.py`).

All ten safe-MISSING settings are now built + wired + tested
(`tests/test_finding3_settings.py` covers the final three).

## Deferred features (33) — NOT settings gaps

These need the underlying feature first (restorer subsystem, slideshow, game-saves
retention policy, shared-store sync, play-loop copy-config-on-play, doc-organiser
auto-run, etc.). Tracked in the migration handoff; listed in `settings_prefs.csv`
with `status=DEFERRED`.
