# Phase 0 — Foundations & cleanup

Goal: a clean Python + PySide6 repo with the platform/path/store foundation the
whole app builds on, plus the housekeeping the old port lacked. No game files are
ever mutated in this phase.

## Done (this slice — repo kickoff)

- **Fresh repo** `vaultkeeper/` (new git history, alongside `nwn_installer_tool_python/`).
- **Dependency & build manifest** — `pyproject.toml` (PySide6 + requests; dev:
  pytest/ruff/mypy; ruff/mypy/pytest config; `vaultkeeper` gui-script). Targets
  Python 3.11–3.13 (PySide6 has no 3.14 wheels yet).
- **Bundled-binary manifest** — `external/tools.toml` (7zz, ffmpeg per-platform,
  with license/version/checksum slots; ERF handled natively = explicit non-dep).
- **Cross-platform game discovery** — `game/locations.py`: native Steam/GOG/Beamdog
  on Win/mac/Linux, **Wine/CrossOver** prefix resolution, **network/UNC** handling;
  `game/editions.py` (EE/Diamond identity, Steam app/workshop ids).
- **Config isolation** — `app_paths.py`: Vaultkeeper's own XDG/Application-Support/
  APPDATA config + relocatable "Vault Store" tree; deliberately does **not** touch
  `Documents/Neverwinter Nights`.
- **Runnable proof** — `python -m vaultkeeper` prints resolved config/store + all
  discovered installs. Verified on the owner's Mac: found the native Steam install
  **and** a CrossOver/Wine install.
- **Tests** — 24 headless tests (locations + app_paths), all green.

## Done (infrastructure services)

- **`core/constants.py`** — domain vocabulary ported from VB, with data-contract
  values **verified against source** (caught that group keys are LazWorks sentinels
  `......000`/`......001`, not friendly names; small-file CRC guard = 5121; folder
  markers; legacy data/map versions).
- **`core/crc.py`** — streaming CRC-32 (native `zlib`, matches VB's stored values).
- **`core/fs.py`** — safe copy/move/delete with permanent-vs-recycle (`send2trash`).
- **`persistence/json_store.py`** — atomic (temp+rename) JSON read/write; corrupt
  files raise rather than silently reset.
- **`config/settings.py`** — one typed, versioned, isolated settings store
  (replaces the old port's two competing settings files); preserves unknown keys.
- **Tests:** 45 total, all green.

## Done (final stretch)

- **`core/log.py`** — single stdlib logging setup (rotating file + console);
  replaces the old port's loguru/stdlib split.
- **`core/message_history.py`** — persistent display-count throttle for
  "don't show again"/diagnostics (ports VB `MessageHistory`/`MessageId`).
- **`game/config_guard.py`** — config-isolation guard: fingerprints the game's
  `nwn.ini`/`settings.tml`, detects added/removed/modified since the last accepted
  baseline, and **never writes game files** (only VK's own snapshot). Powers the
  startup "your game config changed — apply?" prompt.
- **Salvaged binary readers** into `core/formats/` (erf/gff/tga/bic): loguru →
  stdlib logging; removed `src.*` couplings; stripped Qt image conversion out of
  the pure decoders (moves to UI in Phase 7). Verification caught + fixed **real
  latent bugs**: `bic_reader` imported `GffReader` (class is `GFFReader`) and both
  `bic`/`tga` readers were missing `typing` imports (`Tuple`/`List`) that would
  crash at import time.

## Phase 0 status: COMPLETE

- 22 source modules, ~2,740 lines; 10 test files, **89 passing** (+2 pre-existing
  ERF xfails). `ruff` clean, entry point verified on the owner's Mac (native Steam
  + CrossOver/Wine installs discovered).
- Dev env: Python 3.13 (`.venv`), full stack incl. PySide6 6.8.3 validated.

## Next: Phase 1 — domain core

`FileKeyInfo` (equality/comparer semantics first, with tests — winner selection
depends on it), then FileData/InstalledFileData/ModData/GroupMemberData/ChangeData,
the **Mapper** (GetMappedFolder ladder + tables), and a unified **ProfileData**
(load/scan/rebuild/save + state pipeline), all headless. Native store format;
legacy NRBF import stays deferred.

## Notes / decisions

- Package `game/` (not `platform/`) to avoid shadowing the stdlib `platform` module.
- Store lives under the OS data dir by default but is **relocatable to a network
  path**; `VaultStore.is_network()` flags that for availability warnings.
