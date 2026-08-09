"""Move to Folder / Move to History (VB MsMoveToFolder, MsMoveToHistory).

These are the two halves of the documented mod-update workflow
(``dealwithmodupdates.htm``): put the new file in, and keep the old one rather
than deleting it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    payload = tmp_path / "Profiles" / "P" / "Swordflight" / ".Mod Installer"
    (payload / "hak").mkdir(parents=True)
    (payload / "hak" / "sf_v3.hak").write_bytes(b"NEW")
    (payload / "hak" / "sf_v2.hak").write_bytes(b"OLD")
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _files(controller: ProfileController) -> set[tuple[str, str]]:
    md = controller.pd.mod_item("Swordflight")
    return {(fk.folder, fk.filename) for fk in md.files}


def test_the_target_folder_comes_from_the_mapper(controller):
    """A .hak's second home is `patch`, and the caption names it — which is why
    the target is asked for rather than assumed."""
    assert controller.move_target_folder("Swordflight", "hak", "sf_v3.hak") == "patch"
    # Already there: nowhere left to toggle to.
    controller.move_mod_files("Swordflight", "hak", ["sf_v3.hak"], "patch")
    assert controller.move_target_folder("Swordflight", "patch", "sf_v3.hak") == "hak"


def test_an_extension_with_no_second_folder_cannot_move(controller):
    payload = controller.ctx.profile_mods_dir / "Swordflight" / ".Mod Installer"
    (payload / "modules").mkdir()
    (payload / "modules" / "sf.mod").write_bytes(b"M")
    controller.pd.scan_mods(controller.ctx.profile_mods_dir)

    assert controller.move_target_folder("Swordflight", "modules", "sf.mod") == ""


def test_moving_a_file_between_folders(controller):
    result = controller.move_mod_files("Swordflight", "hak", ["sf_v2.hak"], "patch")

    assert result["ok"] and result["moved"] == 1
    payload = controller.ctx.profile_mods_dir / "Swordflight" / ".Mod Installer"
    assert (payload / "patch" / "sf_v2.hak").read_bytes() == b"OLD"
    assert not (payload / "hak" / "sf_v2.hak").exists()
    assert ("patch", "sf_v2.hak") in _files(controller)
    assert ("hak", "sf_v2.hak") not in _files(controller)


def test_moving_to_history_takes_the_file_out_of_the_installer(controller):
    """_History sits beside the payload, not inside it — that is the point.

    The old version is kept, but it is no longer part of what gets installed.
    """
    result = controller.move_mod_files_to_history("Swordflight", "hak", ["sf_v2.hak"])

    assert result["ok"] and result["moved"] == 1
    mod_dir = controller.ctx.profile_mods_dir / "Swordflight"
    assert (mod_dir / "_History" / "sf_v2.hak").read_bytes() == b"OLD"
    assert not any(name == "sf_v2.hak" for _folder, name in _files(controller))
    assert ("hak", "sf_v3.hak") in _files(controller), "the new version stays"


def test_history_keeps_both_when_the_name_repeats(controller):
    """It is a history: a second file of the same name must not erase the first."""
    controller.move_mod_files_to_history("Swordflight", "hak", ["sf_v2.hak"])
    payload = controller.ctx.profile_mods_dir / "Swordflight" / ".Mod Installer"
    (payload / "hak" / "sf_v2.hak").write_bytes(b"OLDER STILL")
    controller.pd.scan_mods(controller.ctx.profile_mods_dir)

    controller.move_mod_files_to_history("Swordflight", "hak", ["sf_v2.hak"])

    history = controller.ctx.profile_mods_dir / "Swordflight" / "_History"
    kept = sorted(p.name for p in history.iterdir())
    assert len(kept) == 2, kept


def test_nothing_selected_is_not_an_error(controller):
    result = controller.move_mod_files("Swordflight", "hak", [], "patch")
    assert result["moved"] == 0 and "None" in result["message"]


def test_the_commands_report_what_happened(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._contents_mod = "Swordflight"

    win._on_move_to_folder()
    assert "Select a file in Contents first." in win.nit_status.mg_info.text()
