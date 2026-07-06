# Phase 3 — UI (PySide6)

Status: **functional scaffold complete.** The app launches and works end-to-end.

## Done (commits d9d876b, c90f93a, fc08832, ecb6603)

- ui/controller.py — ProfileController: UI-free bridge owning ProfileData +
  ModInstallationManager + HakPatchManager. open_profile (load JSON or scan disk),
  groups()/install()/uninstall()/save()/counts()/mod_files().
- ui/main_window.py — MainWindow: three panes (mods tree | contents | details),
  File/Mods menus, status bar counts, state-coloured/installed-marked mods,
  Set Up Profile first-run flow (QFileDialog+QInputDialog), empty-state guidance.
- ui/session.py — bootstrap_controller (settings/discovery -> controller) and
  configure_profile (persist game path+profile, create store, open).
- ui/app.py + __main__ — `python -m vaultkeeper` launches GUI; `--scan` = headless probe.
- conftest sets QT_QPA_PLATFORM=offscreen; ~14 UI tests run headless.

Full suite 246 tests. PySide6 6.8.3 on py3.13.

## Not yet (future UI depth)

- Ribbon/quick-toolbar (salvage the old repo's PyQt6 widgets -> PySide6 pass).
- Details pane richness (properties editing, RTF notes), FileView-style grouped
  list with inline rename/drag-drop, context menus, profile switcher in status bar.
- Settings dialog (Mapper editors, paths, preferences) — Phase 8.
- Config-isolation sync prompt UI (wire game/config_guard at startup).
- Wire dialogs for the other tools (backup, conflicts, character/portrait viewers).
