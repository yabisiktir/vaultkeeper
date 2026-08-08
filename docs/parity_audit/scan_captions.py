"""Rank ported dialogs by VB control captions that have no counterpart in the port.

A coarse but useful net: every VB form's Designer file lists each control's
``.Text``, so a caption whose distinctive words appear nowhere in the ported
dialog is a *candidate* missing control. It is only a candidate — the port may
name the same thing differently, and Designer files are full of placeholder
captions ("ToolStrip1", "Long Sword", "Cave") that mean nothing.

Run it from the repo root with the VB sources beside the checkout:

    python docs/parity_audit/scan_captions.py

Found the Character Explorer's *Only show Ranked Skills* and *Open in Portrait
Manager*, both real; see docs/parity_audit/DIALOG_PARITY.md for the full sweep.
"""
import re
from pathlib import Path

VB = Path("NWN Installer Tool")
PORT = Path("vaultkeeper/src/vaultkeeper/ui/dialogs")

# port dialog file -> VB form name
PAIRS = {
    "alias_section_editor.py": "AliasSectionEditor",
    "basic_settings.py": "BasicSettings",
    "settings_dialog.py": "Settings",
    "dependency_editor.py": "DependencyManager",
    "dependency_manager.py": "DependencyManager",
    "doc_organiser.py": "DocOrganiser",
    "download_project.py": "DownloadProject",
    "game_saves_manager.py": "GameManager",
    "user_response_editor.py": "UserResponseEditor",
    "hak_patch_editor.py": "HakPatchEditor",
    "installation_analyser.py": "InstallationAnalyser",
    "installation_manager.py": "InstallationManagerEditor",
    "mod_play_viewer.py": "ModPlayViewer",
    "play_data_viewer.py": "PlayDataViewer",
    "publish_mod.py": "PublishMod",
    "wizard_builder.py": "WizardBuilder",
    "workshop_viewer.py": "WorkshopViewer",
    "create_missing_installers.py": "CreateMissingInstallers",
    "conflicts_viewer.py": "FileConflictsViewer",
    "character_viewer.py": "CharacterViewer",
    "character_filter.py": "CharacterFilter",
    "start_screen_manager.py": "StartScreenManager",
    "portrait_manager.py": "PortraitManager",
    "mod_explorer.py": "ModExplorer",
    "find_and_rename.py": "ModFindAndRename",
    "create_nwn_folder.py": "CreateNwnFolder",
    "classes_skills_feats.py": "ClassesSkillsAndFeats",
    "common_filters.py": "CommonFiltersDialogue",
    "folder_mapping.py": "Settings",
}

cap = re.compile(r'Me\.(\w+)\.Text = "([^"]{2,60})"')
SKIP = re.compile(r"^(Form|Column|Label\d|LbT|Pic|Tt|Bh|Ss)\w*$")

rows = []
for port_file, form in sorted(PAIRS.items()):
    d = VB / f"{form}.Designer.vb"
    p = PORT / port_file
    if not d.exists() or not p.exists():
        continue
    port_text = p.read_text(encoding="utf-8").lower()
    missing = []
    seen = set()
    for name, text in cap.findall(d.read_text(encoding="utf-8", errors="replace")):
        t = text.strip().rstrip(":").replace("&", "")
        if not t or t.lower() in seen or SKIP.match(name):
            continue
        seen.add(t.lower())
        # A caption counts as present if its distinctive words appear in the port file.
        words = [w for w in re.findall(r"[A-Za-z]{4,}", t)]
        if not words:
            continue
        if not all(w.lower() in port_text for w in words):
            missing.append(f"{name}: {t!r}")
    rows.append((len(missing), form, port_file, missing))

rows.sort(reverse=True)
for n, form, pf, missing in rows:
    if not n:
        continue
    print(f"\n=== {form}  ->  {pf}   ({n} captions with no match)")
    for m in missing[:14]:
        print("   ", m)
    if n > 14:
        print(f"    … and {n-14} more")
