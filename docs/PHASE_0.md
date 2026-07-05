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

## Remaining in Phase 0 (final stretch)

- [ ] Logging + message-history ("don't show again" display-count) service.
- [ ] Startup validation scaffolding for the config-isolation sync prompt
      (detect game-config divergence; never write silently).
- [ ] Salvage triage: copy the KEEP binary readers (erf/gff/tga/bic — pure-stdlib)
      from the old repo into `core/formats` with a verification pass.

## Notes / decisions

- Package `game/` (not `platform/`) to avoid shadowing the stdlib `platform` module.
- Store lives under the OS data dir by default but is **relocatable to a network
  path**; `VaultStore.is_network()` flags that for availability warnings.
