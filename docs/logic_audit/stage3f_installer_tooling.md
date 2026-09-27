# Stage 3f — installer tooling

Method: NIT's `MsAddFiles`, `FileViewPaste` → `InstallerPaste` / `UpdateInstaller`
(which inherits `CreateInstaller` and swaps its scan and create workers),
`PublishMod.BtPublish_Click`, `MsCreateInstaller` / `MsChangeInstaller` /
`ProcessCreateInstaller`, `MsConvertRestorer`, `WizardBuilder.FileThresholdCancel`
and `RunCreateModInstaller` were read line by line and compared with the
controller, `game/installer_build.py` and the dialogs. The help topic
adddownloadedfilestoamod.htm (from the installed CHM) settled where added files go.

| ID | Area | Finding | Verdict |
|---|---|---|---|
| F1 ✅ | Add Files | NIT: "The selected files are moved to your Mod's folder", where Create Installer finds them. VK put them straight into the `.Mod Installer`, which every rebuild recycles and rebuilds from the mod folder. Files added that way were lost on the next rebuild (update, wizard save, Create Installer), and an added archive sat in the installer still packed. Now they go to the mod folder. | BUG (data loss) → fixed |
| F2 ✅ | Update Installer | NIT's paste into a mod's Installer folder runs the items through Create Installer's scan (extract archives, map each file, convert movies) and adds them without clearing the installer. VK had no equivalent. Ported as `update_installer`, with **Paste into Installer** and **Add Files to Installer…** in the Contents menu. VK's Contents list has no Installer folder to paste onto, so the entry point is a menu. | MISSING → ported |
| F3 ✅ | Overwrite toggle | The status bar's Overwrite button (NIT `ui.Overwrite`) was drawn but nothing read it. Add Files and Update Installer now respect it. Its default stays on (NIT `FileOverwrite`: off), so a pasted update replaces what is there. | BUG → fixed; default DELIBERATE |
| F4 ✅ | Publish | 7-Zip's `a` adds into an existing archive, so re-publishing under the same name kept files the mod no longer has. NIT asks "Do you want to replace the current X?" and recycles the old archive first. Ported. | BUG → fixed |
| F5 ✅ | Publish | *Generate Installation Guide* was disabled because the templates were not bundled. NIT's two RTF guides are now in `game/data`. The NWN guide is used when the installer has an `nwn` folder, the manual one otherwise. | MISSING → ported |
| F6 ✅ | Create Installer | With "Install Mods after Installers have been created" on, the rebuild uninstalls an installed mod and VK then skipped reinstalling it *because* it had been installed, leaving it uninstalled. NIT installs every mod built. | BUG → fixed |
| F7 ✅ | Convert Restorer | NIT moves the restorer's folders into `_Downloads` and runs Create Installer, so the mod gets source files. VK only swapped the identifier, leaving the payload only in the installer. With F1 fixed, adding a file and rebuilding would have recycled that payload. Ported: move, rebuild, reinstall if it was installed. | BUG (latent data loss) → fixed |
| F8 ✅ | Wizard Builder | Offer to (re-)create the installer after Save, with "Always take this action" (`ConfigRunCreateInstaller`). | MISSING → ported |
| F9 ✅ | Wizard Builder | Warning when the Archive Folder Files view would list more files than `ConfigWizardFileThreshold` (15,000), with the option to cancel the view change. The setting is not in the Settings dialog yet (nor is `saves_threshold` from 3d). | MISSING → ported |
| F10 | Change Installer | `MsChangeInstaller` just calls `MsCreateInstaller`; VK maps both to the same handler. | same |
| F11 | Publish | Archive name, `-x!` exclusions and the wizard re-rooting for the published archive (`ExtractArchives` forced on, archive prefixes replaced) match. | same |
| F12 | Add Files, BIK | NIT converts `.bik` to `.wbm` while pasting into the mod folder; VK converts when the installer is built. The installer ends up the same. | DELIBERATE |
| F13 | Create Missing Installers | Present (`mods_missing_installer` + the dialog). Not diffed line by line in this stage. | not diffed |

Regression tests: `tests/test_add_files.py` (F1–F3), `tests/test_update_downloads.py`
(F4, F5), `tests/test_wizard_save_creates_installer.py` (F6, F8),
`tests/test_convert_restorer.py` (F7) and `tests/test_wizard_builder.py` (F9). The
F1, F6 and F7 tests fail on the old code.
