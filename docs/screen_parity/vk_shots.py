"""Render Vaultkeeper's counterpart of each NIT form, for screen parity.

Run from vaultkeeper/:  QT_QPA_PLATFORM=offscreen python docs/screen_parity/vk_shots.py [Form ...]
Writes docs/screen_parity/vk/<NIT form name>.png — the same names as the NIT
renders in docs/screen_parity/nit/ (see run_nit_shots.sh), so the two can be
compared side by side. Uses a throwaway profile (one mod, "Alpha"), light theme.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

HERE = Path(__file__).resolve().parent
OUT = HERE / "vk"


def _controller(root: Path):
    from vaultkeeper.core import constants as C
    from vaultkeeper.ui.controller import ProfileController

    mods = root / "Profiles" / "Enhanced Edition Mods"
    payload = mods / "Alpha" / C.MOD_INSTALLER_DIR / "override"
    payload.mkdir(parents=True)
    (payload / "alpha.2da").write_text("2DA V2.0\n")
    user = root / "home" / "Documents" / "Neverwinter Nights"
    _populate_user_dir(user)
    return ProfileController.open_profile(
        profile_mods_dir=mods,
        game_root=root / "NWN",
        game_user_dir=user,
        store_path=root / "Data" / "Enhanced Edition Mods.json",
        settings_path=root / "settings.json",
    )


#: The [Alias] section of a stock EE nwn.ini (as NIT's sandbox render shows it).
_ALIASES = [
    "AMBIENT", "CACHE", "CRASHREPORT", "CURRENTGAME", "DATABASE", "DEVELOPMENT",
    "DMVAULT", "HAK", "LOCALVAULT", "LOGS", "MODELCOMPILER", "MODULES", "MOVIES",
    "MUSIC", "NWSYNC", "OLDSERVERVAULT", "OVERRIDE", "PATCH", "PORTRAITS", "SAVES",
    "SCREENSHOTS", "SERVERVAULT", "TEMP", "TEMPCLIENT",
]


def _populate_user_dir(user: Path) -> None:
    """A throwaway EE user folder like NIT's sandbox one: aliases, patch haks, a save."""
    lines = ["[Alias]", f"HD0={user}"]
    for alias in _ALIASES:
        folder = user / alias.lower()
        folder.mkdir(parents=True, exist_ok=True)
        lines.append(f"{alias}={folder}")
    (user / "nwn.ini").write_text("\n".join(lines) + "\n")
    for hak in ("cep2_patch", "prc8_patch"):
        (user / "patch" / f"{hak}.hak").write_bytes(b"HAK V1.0")
    (user / "hak" / "alpha.hak").write_bytes(b"HAK V1.0")
    (user / "override" / "alpha.2da").write_text("2DA V2.0\n")
    save = user / "saves" / "000001 - Alpha Start"
    save.mkdir(parents=True)
    (save / "savename.txt").write_text("Alpha Start")


def _builders(c):
    """NIT form name -> callable returning the VK widget to render."""
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.dialogs import (
        alias_section_editor,
        backup_manager,
        basic_settings,
        character_viewer,
        create_missing_installers,
        dependency_manager,
        download_project,
        extended_edition,
        find_and_rename,
        find_files,
        game_saves_manager,
        hak_patch_editor,
        installation_analyser,
        installation_manager,
        mod_explorer,
        mod_play_viewer,
        publish_mod,
        settings_dialog,
        user_response_editor,
        wizard_builder,
        workshop_viewer,
    )
    from vaultkeeper.ui.main_window import MainWindow

    return {
        "NIT": lambda: MainWindow(c),
        "AliasSectionEditor": lambda: alias_section_editor.AliasSectionEditor(c),
        "BackupManager": lambda: backup_manager.BackupManager.show_for(c),
        "BasicSettings": lambda: basic_settings.BasicSettingsDialog(Settings()),
        "CharacterViewer": lambda: character_viewer.CharacterViewer.show_for(c),
        "CreateMissingInstallers": lambda: create_missing_installers.CreateMissingInstallers(c),
        "DependencyManager": lambda: dependency_manager.DependencyManager.show_for(c),
        "DownloadProject": lambda: download_project.DownloadProjectDialog(c),
        "ExtendedEditionDialogue": lambda: extended_edition.ExtendedEditionDialog(),
        "FindProfileFilesDialogue": lambda: find_files.FindFilesDialog(c),
        "GameManager": lambda: game_saves_manager.GameSavesManager.show_for(c),
        "HakPatchEditor": lambda: hak_patch_editor.HakPatchEditor(c),
        "InstallationAnalyser": lambda: installation_analyser.InstallationAnalyser(c),
        "InstallationManagerEditor": lambda: installation_manager.InstallationManager(c),
        "ModExplorer": lambda: mod_explorer.ModExplorer.show_for(c),
        "ModFindAndRename": lambda: find_and_rename.FindAndRenameDialog(c),
        "ModPlayViewer": lambda: mod_play_viewer.ModPlayViewer.show_for(c),
        "PublishMod": lambda: publish_mod.PublishMod(c, "Alpha"),
        "Settings": lambda: settings_dialog.SettingsDialog(Settings()),
        "UserResponseEditor": lambda: user_response_editor.UserResponseEditor(c),
        "WizardBuilder": lambda: wizard_builder.WizardBuilder(c, "Alpha"),
        "WorkshopViewer": lambda: workshop_viewer.WorkshopViewer(c),
        **_more_builders(c),
    }


def _more_builders(c):
    """The second pass: the forms not paired in the first."""
    from PySide6.QtWidgets import QTextEdit

    from vaultkeeper.ui.dialogs import (
        character_filter,
        classes_skills_feats,
        common_filters,
        conflicts_viewer,
        crash_reports,
        create_nwn_folder,
        doc_organiser,
        find_text,
        image_viewer,
        old_downloads,
        play_data_view_pending,
        play_data_viewer,
        portrait_manager,
        start_screen_manager,
    )

    picture = c.ctx.game_user_dir / "portraits" / "po_alpha_h.png"

    def image():
        from PySide6.QtGui import QColor, QImage

        img = QImage(128, 200, QImage.Format.Format_RGB32)
        img.fill(QColor("steelblue"))
        img.save(str(picture))
        return image_viewer.ImageViewer(picture)

    return {
        "CharacterFilter": lambda: character_filter.CharacterFilter(["Fighter", "Wizard"]),
        "ClassesSkillsAndFeats": lambda: classes_skills_feats.ClassesSkillsAndFeatsDialog(),
        "CommonFiltersDialogue": lambda: common_filters.CommonFiltersDialog(
            ["Worth Playing"], ["Good"], {"Worth Playing": True}, {"Good": True}
        ),
        "CrashDumpManager": lambda: crash_reports.CrashReportsDialog(c),
        "CreateNwnFolder": lambda: create_nwn_folder.CreateNwnFolderDialog(profile_name="Test"),
        "DocOrganiser": lambda: doc_organiser.DocOrganiser(c, ["Alpha"]),
        "DownloadDeleteMsg": lambda: old_downloads.OldDownloadsDialog("Alpha", []),
        "FileConflictsViewer": lambda: conflicts_viewer.ConflictsViewer.show_for(c),
        "FindDialogue": lambda: find_text.FindTextDialog(QTextEdit()),
        "MsgPicture": image,
        "PlayDataViewPending": lambda: play_data_view_pending.PlayDataViewPending.show_for(c),
        "PlayDataViewer": lambda: play_data_viewer.PlayDataViewer.show_for(c),
        "PortraitManager": lambda: portrait_manager.PortraitManager.show_for(c),
        "StartScreenManager": lambda: start_screen_manager.StartScreenManager.show_for(c),
    }


def _isolate(root: Path) -> None:
    """Keep every path this script can reach inside ``root`` (like tests/conftest).

    ★ Without this an EE profile falls back to the REAL ~/Documents/Neverwinter
    Nights: opening the Game Saves Manager here once moved two of the owner's saves
    into this script's temporary store, which was then deleted (2026-09-28).
    """
    import os

    import nwnfile.locations
    import send2trash

    import vaultkeeper.app_paths

    home = root / "home"
    (home / "Documents" / "Neverwinter Nights").mkdir(parents=True)
    os.environ["HOME"] = str(home)
    for var in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        os.environ[var] = str(home / var.lower())
    vaultkeeper.app_paths._home = lambda: home
    nwnfile.locations._home = lambda: home
    bin_dir = root / "recycle-bin"
    bin_dir.mkdir()
    send2trash.send2trash = lambda path: Path(path).rename(bin_dir / Path(path).name)


def _actions(widget) -> list[str]:
    """Every action a user can take on ``widget``: button, check box, menu and toolbar captions."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QAbstractButton, QMenu, QTabWidget, QToolButton

    seen: list[str] = []

    def add(kind: str, text: str) -> None:
        text = text.replace("&", "").strip()
        if text and f"{kind}\t{text}" not in seen:
            seen.append(f"{kind}\t{text}")

    for button in widget.findChildren(QAbstractButton):
        if isinstance(button, QToolButton) and button.defaultAction() is not None:
            continue
        add(type(button).__name__, button.text() or button.toolTip())
        menu = button.menu() if hasattr(button, "menu") else None
        if isinstance(menu, QMenu):
            for act in menu.actions():
                add("MenuItem", act.text())
    for act in widget.findChildren(QAction):
        add("Action", act.text())
    for tabs in widget.findChildren(QTabWidget):
        for i in range(tabs.count()):
            add("Tab", tabs.tabText(i))
    return seen


def main(wanted: list[str]) -> None:
    app = QApplication.instance() or QApplication([])
    from vaultkeeper.ui.theme import apply_appearance

    apply_appearance(app, font_point_size=0, theme="light")
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        _isolate(Path(tmp))
        c = _controller(Path(tmp))
        real = Path(os.path.expanduser("~")).resolve()
        assert str(c.ctx.game_user_dir or "").startswith(tmp) or c.ctx.game_user_dir is None, (
            f"refusing to render: game folder {c.ctx.game_user_dir} is outside {tmp} ({real})"
        )
        for name, build in _builders(c).items():
            if wanted and name not in wanted:
                continue
            try:
                widget = build()
                widget.show()
                app.processEvents()
                widget.grab().save(str(OUT / f"{name}.png"))
                (OUT / f"{name}.controls.txt").write_text("\n".join(_actions(widget)) + "\n")
                widget.close()
                print(f"{name}: ok")
            except Exception as exc:  # noqa: BLE001 - report and go on
                print(f"{name}: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main(sys.argv[1:])
