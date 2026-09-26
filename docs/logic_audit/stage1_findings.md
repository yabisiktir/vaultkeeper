# Stage 1 — install core: function diffs

Status per function group. Triage labels: **BUG** (VK worse than NIT),
**DELIBERATE** (VK chose differently, documented), **VERIFY** (needs stage 2 to
see the real effect), **PLATFORM** (difference only because of the OS).

## 1a. File Mapper — DONE

Corpus: 39,239 mod-relative paths (`stage1/build_corpus.py`): 2,711 from the
Vaultkeeper store's installer folders, 20,024 from `7z l` listings of the NWN
archives (no extraction), 841 real file names from the NWN user folder, 15,663
synthetic edge cases generated from both apps' tables.
Five questions per path, in both first-run modes (Player, Builder):
196,195 answers per mode. Runner: `stage1/run_mapper_diff.py`.

Table diff (NIT's live tables dumped by the harness vs `Mapper(is_ee=True)`):
identical except the rows below; player exclusions match once VK's
`apply_player_excludes()` (its first-run Player answer) is applied.

**Result: 3,234 mismatches per mode, all explained by two root causes; zero
residual.** Every real-data path (store/archive/userdir) agrees except 10 store
files under `nitconfig/` (cause B).

| # | Finding | Count | Triage |
|---|---|---|---|
| M1 | **EE folder rules missing.** NIT's `DefineEeFolders` adds `DirMapping` entries `ovr`, `mus`, `txpk` and the EE `mod` folder, so a mod that ships files inside those folders installs them there. VK ported the *paths* of those folders (`nwn_folder_paths`) but not the *dir-mapping* entries, so the files are routed by extension instead (e.g. `ovr/x.2da` → `override`, `txpk/x.erf` → `erf` rules). Affects any mod laid out for the EE library (Community Patch-style `ovr/`, texture packs in `txpk/`). | 2,848 | **BUG** |
| M2 | **`nitconfig` always excluded.** VK's `contains_excluded_folder` treats every `nitconfig` folder as excluded (commented as deliberate: "identifier metadata, never a copy source"). NIT excludes it only under the extracted-zips area. Effect to check: re-creating an installer from a mod folder that carries `nitconfig/*.nitins|*.nitres` identifiers. | 386 | DELIBERATE → **VERIFY** in stage 2 |

Also noted by reading while building the harness (no mismatch in the corpus,
recorded so stage 4 doesn't re-derive it):
- NIT's `Mapper.vb` is `Option Compare Text`, so `folder <> sourceFolder` is
  case-insensitive; VK compares the folder-moves source case-insensitively too,
  but `folder != source_folder` is case-sensitive. No corpus path distinguishes
  them (the second clause is case-insensitive in both).
- VK `contains_excluded_folder` matches per path component, NIT substring-matches
  the whole path. No corpus difference because the exclude names are distinctive;
  a folder like `my scripttemplates backup` would differ (NIT excludes).

## 1b. Mod name from a pasted/dropped source — DONE

NIT: `NIT.Paste.vb` `ModPasteInfo(group, source).ModName` (`ModNameFromFile`: folder
name, or file name without extension → LazWorks `ToSentence`, `_`→space, acronyms
upper-cased, small words lower-cased, `vNN` lower-cased, roman numerals upper-cased,
`qNN` → "Project Q vNN"). VK: `controller.paste_mods` uses the name **verbatim**
(docstring: "NOTE (divergence)"). Corpus: 289 real names (every archive stem and
mod folder in the live download rules, plus edge cases). Harness query `modname`.

| # | Finding | Count | Triage |
|---|---|---|---|
| N1 | NIT tidies raw archive names (`8191_overrides` → "8191 Overrides", `angel_falls_prelude_v24` → "Angel Falls Prelude v24"); VK keeps `angel_falls_prelude_v24` as the mod name. | 197 / 289 | **BUG** (VK worse for the common case: archive names are usually raw) |
| N2 | NIT damages already-clean names: "Tales of Arterra ( EE)", "The  Aielund  Saga", "Mid- Winter- Summer- Night Series" (its CamelCase splitter treats `(`, `-`, `_`+capital as word breaks). VK keeps them intact. | 20 / 289 | VK better |
| N3 | NIT restyles clean names ("and" → "And", "CEP v2.x" → "CEP V2.x"). | 13 / 289 | neutral |

Fix direction: port the tidy-up for raw names (underscores, all-lower words,
acronyms, vNN, Project Q) **without** the CamelCase splitter that causes N2.

## 1e. Change tracking — moved to stage 2

`ChangeData` is only a container; detection happens when the profile is
rescanned against disk (`ProfileData` load/validate). Compared in stage 2 by
changing files outside the app and rescanning.

## 1c. Vault download rules — DONE (parse level)

Method: the harness builds NIT's `VaultDownloadRules` and serialises every
parsed `ProjectInfo` (all public properties, recursively, incl. `Wizard`) to
`stage1/nit_rules_dump.txt`; `stage1/diff_rules.py` parses the **same file** with
Vaultkeeper's `DownloadRules.from_text` and compares.

Input note: NIT **downloads the current rules at start-up** (2,602 lines, today)
instead of using its bundled copy (2,549 lines), as Vaultkeeper does. The first
diff mixed the two files; the recorded result uses the file NIT actually read.

Vaultkeeper's own docstring calls its parser "the subset the port currently
uses". Measured on the live rules: NIT 239 projects, VK 227.

| # | Finding | Projects | Triage |
|---|---|---|---|
| R1 | **Per-project `ExcludeFiles From <project>` blocks ignored.** The top-level `ExcludeRules` section names files to hold back per project (Arena Tileset's test `arena.mod`, Winter 6's loose `.hak`, older Wizard's Challenge zips, Bioware Premium trailer…). NIT applies them; VK doesn't parse the syntax, so those files are offered/downloaded. Also explains the 12 "missing" projects and the `d20 modern` / `nwn save editor` exclude gaps. | 12 + 2 | **BUG** |
| R2 | **Edition conditionals (`If EE Downloads` / `If NWN Downloads`) dropped.** NIT picks the edition's `ModFolder` and download whitelist; VK discards the block. Community Patch 1.72 and Community Patch Project lose their mod folder *and* their EE archive; Sea of Shadow, Real Skies, Runes of Blood, Project Q, Tales of Arterra, Sanctum, Surviving Horror, Witcher placeables, Community Music Pack, Custom Menus get a wrong/empty whitelist. | 4 mod folders, 12 whitelists | **BUG** |
| R3 | **Rule-defined install wizards never used.** 38 projects carry a wizard (13 SelectOne, 16 SelectMany, 15 ExtractArchives, 17 InstallerExcludes). NIT applies it on download, installer creation, the install worker, Portrait Manager, Workshop import, and pre-fills Wizard Builder (`GetWizardInfo`, 6 call sites). VK's wizard engine (`game/wizard.py`) only reads wizards shipped in a mod. | 38 | **BUG** |
| R4 | **Per-file prerequisites (`RequiredFiles From <project>`) ignored.** NIT downloads only the named files of a required project; VK has project-level prerequisites only. | 32 | **BUG** |
| R5 | `IncludeExtensions` (7), `ExcludeDirectLinks` (6), `ApplyExcludes = False` (6), `ExcludeRequiredProjects` (4), `ExternalFile` (1) not parsed. Each changes which files a download offers. | 26 | **BUG** (lower impact each) |
| R6 | NIT keeps the literal line `End Exclude` as an excluded *file name* (two Aielund projects); VK doesn't. | 2 | VK better |
| R7 | NIT decodes `’` in one prerequisite URL as U+FFFD; VK decodes cp1252 correctly. | 1 | VK better |
| R8 | Coldhearth exclude list differs in content (to inspect). | 1 | **VERIFY** |

Next for 1c: these are parse-level results. Stage 2 should run the *download
selection* itself (which files each app offers/ticks for a project) on a few of
the affected projects, with the Vault responses recorded once and replayed to
both apps (no repeated downloads, no disk cost).
## 1d. Dependency + conflict detection — moved to stage 2

`GetConflicts`, `HasDependants`, `GetDependants`, `GetInstalledDependants`,
`GetAutoDependencyList`, `ValidateDependencies` all read the loaded profile
(`pd`), so they are only meaningful after real installs. They are compared in
stage 2 after each scripted step.
