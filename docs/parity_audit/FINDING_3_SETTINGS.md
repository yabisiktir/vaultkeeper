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

## Built this pass

- **`ConfigDefaultGroup`** → `Settings.default_group` + wired into
  `controller.create_mod` (new mods land in the chosen group; empty = ungrouped)
  + a "Default group for new mods" field on the Settings Behaviour tab.
  Tests: `tests/test_default_group.py`.

## Backlog — remaining 9 safe-MISSING settings (behaviour exists, add a toggle)

Add each as a `Settings` field + a Behaviour-tab control + wire to the existing
behaviour (do NOT add without wiring):

- `BehaviourUninstallDependencies` — cascade uninstall to installed dependents
  (port has the dependency graph + uninstall).
- `BehaviourConfirmActions` / `BehaviourConfirmSaves` — gate the confirm prompts.
- `ConfigDeleteLetoLogs` — auto-run the existing `remove_leto_log_files`.
- `ConfigDisplayTgaImages` / `ConfigDisplayStdImages` / `BehaviourDisplayImageFiles`
  — toggle the existing image preview (DisplayInfo / ImageViewer).
- `ConfigPortraitDisplaySize` — default size for the Portrait Manager preview.
- `BehaviourMoveAddedMods` — move added mods into the default group on add.

## Deferred features (33) — NOT settings gaps

These need the underlying feature first (restorer subsystem, slideshow, game-saves
retention policy, shared-store sync, play-loop copy-config-on-play, doc-organiser
auto-run, etc.). Tracked in the migration handoff; listed in `settings_prefs.csv`
with `status=DEFERRED`.
