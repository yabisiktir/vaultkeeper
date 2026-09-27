# Stage 3h — Steam Workshop

Method: NIT's `SteamWorkshop.vb` (`LoadContent`, `ValidateSteamContent`, `LoadMods`,
`UnsubscribeAll`, `Unsubscribe`, `RetainModQuestion`, `ValidateModContent`,
`UpdateRequired`, `CreateMods`, `CreateInstallers`), `SteamWorkshop.ModInfo`
(`SteamOnly`, `CheckResubscribed`, `CreateModFolder`, `UpdateWorkshopFile`),
`SteamWorkshop.IdInfo` (`GetModFolderName`, `ModNameFromWeb`, `RefreshSteamFiles`)
and `VaultDownloadRules` `WorkshopIdMap` were compared with `game/workshop.py`, the
controller and the Workshop UI.

| ID | Area | Finding | Verdict |
|---|---|---|---|
| W1 ✅ | New subscriptions | With management on, NIT creates a mod in the Workshop group for each new subscription, packs it, builds it and installs it when the profile loads. VK only reported a summary; a mod was made only by a manual Add in the Workshop viewer, and that mod was not installed. | MISSING → ported (`sync_workshop_mods`) |
| W2 ✅ | Changed subscriptions | NIT repacks a managed mod's Workshop archive and rebuilds its installer when Steam changes the item's files. VK never did, so the game kept the old version. VK compares with what was last packed (recorded per item) rather than the installer's CRCs; the startup summary refreshes the database whether or not management is on, and a database diff would have lost a change seen then. | BUG → fixed |
| W3 ✅ | Unsubscribed | NIT asks "Do you want to keep X?" (keep = cut the Steam link; no = delete the mod), with "Take the same action for all". VK left the mod linked to a subscription that no longer exists and never asked. | MISSING → ported |
| W4 ✅ | Stop Managing → delete | Dropped only the mod definitions: their files stayed in the game, owned by nothing, and their folders stayed on disk. NIT deletes (uninstall, recycle, anneal). | BUG → fixed |
| W5 ✅ | Turning management off | NIT asks what to do with the managed mods (`UnsubscribeAll`); VK changed the setting and nothing else. Now the Stop Managing question runs; turning it on runs the sync. | MISSING → ported |
| W6 ✅ | Duplicates | NIT does not create a Workshop mod for a module another mod already installs (`SteamOnly`, e.g. the same module from the Vault). | MISSING → ported |
| W7 ✅ | Naming | NIT: `MapId` rule → Steam page title → first `.mod` → `Mod <id>`. VK parsed no `MapId` rules (21 in the published file) and never read the title, so haks and override packs came in as `Mod <id>`. The title is fetched only while management is on. A name the user gave in the viewer was ignored when creating the mod; now used. | BUG → fixed |
| W8 ✅ | Repacking | 7-Zip's `a` adds into an existing archive; NIT deletes the old one first. VK did not (it only packed once, until W2). | fixed |
| W9 | Unknown names | NIT asks for a name (`WorkshopNameEditor`) for each item still called `Mod <id>` when content loads; VK leaves the name and offers Rename in the Workshop viewer. | DIFFERENT (not ported) |
| W10 | Change detection | NIT: checksums; VK: size + modified time. A file touched without changing makes VK repack once. | DELIBERATE (cheaper, same outcome) |
| W11 | Status line, NIT | NIT's `LoadContent` tests `Added > 0` for the Updated and Deleted counts too. | NIT artefact |

Regression tests: `tests/test_workshop_sync.py` (13) and
`tests/test_stop_managing_workshop.py`.
