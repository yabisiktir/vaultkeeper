# Working in Vaultkeeper

Guidance for any AI/automation session (and humans) touching this repo. Read this
before editing UI code.

## Theming — do not neglect it

Vaultkeeper ships **light / dark / system** appearance. Theming here has bitten us
more than once; treat these as rules, not preferences.

1. **The palette only works under the Fusion style.** The native Qt styles paint
   their chrome from the OS appearance and ignore most of an application palette —
   on macOS that left the toolbar and ribbon tab-strip dark while the panels below
   went light (two halves of different themes). `theme.apply_appearance` switches
   to `Fusion` *before* setting the palette for exactly this reason (see
   `src/vaultkeeper/ui/theme.py`). **Do not** set a colour scheme by any path that
   bypasses `apply_appearance`, and don't reintroduce a native style for themed
   windows.

2. **Read colours from the palette / theme helpers, not hardcoded hex.** Status
   colours come from `theme.status_colour()` / `default_status_colour()`, which
   resolve per light/dark via `theme.is_dark()`. A literal hex in a widget will be
   wrong in one of the two themes. New surfaces must derive their colours from the
   active `QPalette` or these helpers so both themes stay correct.

3. **"system" must be reversible.** `apply_appearance` captures the base style and
   palette on first run and restores them for `system`; a replaced palette cannot
   be un-set otherwise (choosing "system" after dark left the window dark until
   restart). If you touch appearance state, preserve that capture/restore.

4. **Verify both themes, and the opposite OS appearance.** An offscreen render
   uses a light-ish default palette and hides dark-mode leakage. Force a dark
   system palette (`app.setPalette(...)` with Window/Base dark) and confirm no
   surface falls back to it.

The editor window Vaultkeeper embeds (from `nwn-save-editor`) has its **own**
token-based theming — see that repo's `CLAUDE.md`. When Vaultkeeper opens it, the
controller acts as its host and may dictate the theme via `editor_theme()`.

## Before you push

Run the same gate CI runs (from the `vaultkeeper/` dir):

```bash
scripts/check.sh
```

It runs the bundled-7-Zip check, the full pytest suite headless
(`QT_QPA_PLATFORM=offscreen`), then `ruff check src tests scripts docs`. A
pre-commit hook lints on every commit — activate it once with:

```bash
git config core.hooksPath .githooks
```

Ruff must pass cleanly; don't redirect its output away and read only pytest — that
is how a lint slip reaches CI, which is what this guardrail exists to stop.
