# NIT v8.0 against the port

NIT v8.0 was released on 8 August 2026: 6 bug fixes, 3 improvements, 9
miscellaneous. Every item below was checked against this port by reading the VB
diff, not by reading the changelog — several turned out not to apply, and two
turned out to be gaps the port had independently of v8.0.

## Ported

| v8.0 item | What landed here |
|---|---|
| **Download Project uses the Vault's API** | Both sources kept, chosen under **Settings → Downloads** (`vault_download_method`). The API is the default. See [vault_downloads.md](../vault_downloads.md). |
| *(the author's own request)* **the Download Rules file is retrieved online** | `vault/rules_source.py`: two published hosts, a day's cache, the file bundled as an offline floor. The port previously read only a local file nothing created, so it ran with **no rules at all**. |
| **Validate Mod Web Links** (Tools) | Full pass with the five report sections, a background thread, and an *Update* that writes back only unambiguous corrections. |
| **Find Mod's Web Page Link** (Edit) | Identified by the files the mod holds; a name-only match is offered but never written without confirmation. |
| **Check for Mod Updates** (Edit) | Opens Download Project on the mod's own link, already fetched. |
| **Required Projects that are web pages, not files** | Labelled *(external page)* and opened in the browser. The API states the kind; a scraped page is judged by its URL. |
| **Old download versions offered for deletion** | Offered after any download, not only for No-Installer projects, with *Keep in _History* as the default answer. |
| **Daily play-time average counts days not played** | And the floor of 1 is gone, so it can answer zero. |
| *(v8.0 internal)* **the project URL is recorded on the mod** | Both from Download Project and from Install PRC Module — the latter a gap the link work exposed, since a PRC repack's filenames match no Vault page. |

## Does not apply to this port

| v8.0 item | Why |
|---|---|
| Nexus rejects programmatic Add Link | Link validation here is syntactic (`core.urls.is_url`); no URL is ever fetched to check it. |
| Portrait Manager ignores Map Excluded Folders | Editability comes from the installed-file list and the wizard's own sources, both already mapped. There is no raw `_Downloads` scan to exclude from. |
| Alias Section Editor per-profile saves location | The per-profile toggle is not ported (recorded as deferred); alias values are written directly. |
| Recent Items not unpinned | A Windows jump-list behaviour. The port's Recent Mods is a menu with no pinning. |
| Fewer web-request error messages | The port logs failures and shows one status line; it never had a message box per request. |
| Message Position / Message Position Adjustments | Both position the notice shown while the NWN Toolset is running. The port shows no such notice. |
| Copy to Shared NIT Store | Gated on a shared store, which is a standing non-goal — mod export/import is ported instead. |
| Windows Title Bar Colour | A Win32 DWM attribute. |
| Notepad++ DownloadRules language file | Editor tooling, not application behaviour. |

## Still open

* **The rules file's 224 per-project blocks** (`Project … ModFolder … Group …
  ExcludeFiles … RequiredFiles`) are not parsed. They give a downloaded project
  its mod folder and group automatically; here both come from the dialog.
