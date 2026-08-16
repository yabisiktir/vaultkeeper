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

## Syncing from upstream NIT

Vaultkeeper began as a Python reimplementation of the VB.NET NWN Installer Tool
(NIT) and has since grown its own features. **Vaultkeeper's current behaviour is the
baseline — parity with NIT is not the goal.** Don't revert or reshape evolved code
to match the original.

Going forward we periodically review **newer NIT releases** and bring relevant fixes
and new features across, layered on top of what Vaultkeeper already has. When you do
that:

1. **Read the NIT VB source as the reference for the new behaviour**, and when a new
   screen or control comes across, reuse its UI idiom — the `.Image` lines in the VB
   `<Form>.Designer.vb` give the original icons rather than a text-button stand-in.
2. **Add onto Vaultkeeper's existing implementation; don't replace it** to look like
   NIT. Where Vaultkeeper already diverged deliberately, keep the divergence.
3. **The coverage ledger in `docs/parity_audit/` is a provenance map** of what came
   from which NIT construct (it tracks specific NIT versions, e.g. `NIT_V8.md`) — use
   it to diff a new release and find what's new, not as a spec to conform to.

## User-data safety

Vaultkeeper writes into the user's real NWN install and save folders. Losing their
mods or saves is the worst thing it can do.

1. **Deletions go through the recycle bin, not `unlink`.** `send2trash` is used so a
   mistake is recoverable; a test proves it (the autouse `recycle_bin` fixture
   redirects it). Don't hard-delete user content.
2. **A data-loss bug already shipped once** (Rebuild-Database wiped user data). The
   conftest `_isolate_store` fixture that keeps tests off the developer's real store
   exists because of it — **keep it**, and never let a code path write to the real
   config/data root in a test.
3. **Resolve the EE user directory correctly.** On Enhanced Edition, installed
   content lives in the **user** dir, located via `nwn.ini`'s `[Alias]` section — not
   a guessed `Documents` path (`app_paths.py` / `verify_install.py`). A shared user
   folder cannot serve two OSes: the aliases are absolute and platform-specific.

## Downloads and the vault API

1. **Downloads must stream.** A 1.2 GB hakpak read into memory crashed the app. Use
   the streaming path (`vault/downloader.py`, `vault/http.py`, `vault/drive_download.py`
   — chunked `iter_content`), never `response.content` on a mod file.
2. **The download rules are fetched, not bundled** (`vault/download_rules.py`); NIT
   v8's API replaced scraping (scraping is now a fallback setting, `vault/scraper.py`).
   Beware the **cp1252** encoding on vault responses. Don't hardcode or vendor the
   rules file.

## Testing conventions

- **The autouse isolation fixtures are load-bearing — never remove them.**
  `_isolate_store` patches `app_paths._home` *and* the `config_root`/`data_root`/
  `cache_root` env vars (patching `_home` alone is not enough off macOS);
  `recycle_bin` redirects `send2trash`. They keep the suite off the developer's real
  files.
- **Real-data tests are env-gated and skip by default.** They read the tester's
  actual install via `VAULTKEEPER_TEST_NIT_STORE` / `_NWN_USER_DIR` / `_NWN_INSTALL`
  / `_STEAM_WORKSHOP` (see `tests/real_data.py`) and `skipif` when unset. Assert
  shapes and ranges, not exact real-world values.
- **GUI tests run headless** (`QT_QPA_PLATFORM=offscreen`); a modal dialog on the
  path under test will hang the run. Steer past it or patch it.

## Cross-platform

This ships on **Windows, macOS and Linux** (and CrossOver). Paths, the user
directory and the alias handling differ per OS — none of it was verified on the
other OSes until CI started doing it, and the first real run found bugs. Don't
assume a macOS-shaped path or a single user-folder layout; go through `app_paths`
and the platform helpers.

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
