"""Moving a mod between machines (VB ``ModExport`` + the shared-store import).

The original does this through a live network share. This ports the outcome as a
single ``.vkmod`` archive, so the interesting cases are the ones VB is careful
about: the local completion history must survive an import, play times must
merge rather than be replaced, and ``_Downloads`` must not be dragged along
unasked — it is routinely the largest part of a mod.
"""

from __future__ import annotations

import os
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from vaultkeeper.core import constants as C
from vaultkeeper.game.mod_transfer import RECORD_NAME, SUFFIX, describe
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _make_mod(controller, name: str, *, group: str = "", downloads: bytes | None = None):
    controller.create_mod(name, group or None)
    folder = controller.ctx.profile_mods_dir / name
    installer = folder / C.MOD_INSTALLER_DIR / "hak"
    installer.mkdir(parents=True, exist_ok=True)
    (installer / "a.hak").write_bytes(b"HAKDATA")
    if downloads is not None:
        dl = folder / C.DOWNLOADS_DIR
        dl.mkdir(parents=True, exist_ok=True)
        (dl / "source.7z").write_bytes(downloads)
    return folder


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def test_export_writes_one_archive_per_mod(tmp_path: Path):
    controller = _controller(tmp_path)
    _make_mod(controller, "Alpha", group="Community")
    _make_mod(controller, "Beta")

    out = tmp_path / "out"
    result = controller.export_mods(["Alpha", "Beta"], out)

    assert len(result["exported"]) == 2
    assert (out / f"Alpha{SUFFIX}").is_file()
    info = describe(out / f"Alpha{SUFFIX}")
    assert info is not None
    assert info.mod_name == "Alpha"
    assert info.group == "Community"
    assert info.file_count >= 1


def test_downloads_are_left_out_unless_asked_for(tmp_path: Path):
    # _Downloads holds the original archives and is usually the bulk of a mod;
    # another machine only needs them to *rebuild* an installer.
    controller = _controller(tmp_path)
    _make_mod(controller, "Alpha", downloads=b"X" * 4096)

    out = tmp_path / "out"
    controller.export_mods(["Alpha"], out)
    with zipfile.ZipFile(out / f"Alpha{SUFFIX}") as archive:
        names = archive.namelist()
    assert not any(C.DOWNLOADS_DIR in n for n in names)
    assert not describe(out / f"Alpha{SUFFIX}").has_downloads

    controller.export_mods(["Alpha"], out, include_downloads=True)
    with zipfile.ZipFile(out / f"Alpha{SUFFIX}") as archive:
        names = archive.namelist()
    assert any(C.DOWNLOADS_DIR in n for n in names)
    assert describe(out / f"Alpha{SUFFIX}").has_downloads


def test_a_group_row_is_not_exportable(tmp_path: Path):
    controller = _controller(tmp_path)
    controller.create_group("Just A Group")
    result = controller.export_mods(["Just A Group", "Nope"], tmp_path / "out")
    assert result["exported"] == []
    assert sorted(result["skipped"]) == ["Just A Group", "Nope"]


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
def test_round_trip_into_a_fresh_profile(tmp_path: Path):
    source = _controller(tmp_path / "machine-a")
    _make_mod(source, "Alpha", group="Community")
    source.pd.mod_item("Alpha").web_link = "https://example.invalid/alpha"
    source.save_notes("Alpha", "Remember the second key.")
    out = tmp_path / "carried"
    source.export_mods(["Alpha"], out)

    target = _controller(tmp_path / "machine-b")
    result = target.import_mods([out / f"Alpha{SUFFIX}"])

    assert result["imported"] == ["Alpha"]
    md = target.pd.mod_item("Alpha")
    assert md is not None
    assert md.group == "Community"
    assert md.web_link == "https://example.invalid/alpha"
    assert "Community" in target.pd.mod_list, "the group came with it"
    # The payload landed, and the profile knows about it.
    hak = target.ctx.profile_mods_dir / "Alpha" / C.MOD_INSTALLER_DIR / "hak" / "a.hak"
    assert hak.read_bytes() == b"HAKDATA"
    assert any(fk.filename == "a.hak" for fk in md.files)
    # Byte-for-byte: notes live as RTF, so the file travels as-is rather than
    # being re-wrapped on the way in.
    assert target.read_notes("Alpha") == source.read_notes("Alpha")
    assert "Remember the second key." in target.read_notes("Alpha")


def test_your_own_completion_history_survives_an_import(tmp_path: Path):
    """VB preserves the target's DateCompleted/CompletedCount on import.

    They describe *your* play, not the mod, so taking the other machine's would
    quietly rewrite your history — and for a mod you have never played, being
    handed somebody else's completion count is worse still.
    """
    source = _controller(tmp_path / "a")
    _make_mod(source, "Alpha")
    source.pd.mod_item("Alpha").completed_count = 7
    source.pd.mod_item("Alpha").date_completed = datetime(2020, 1, 1)
    out = tmp_path / "carried"
    source.export_mods(["Alpha"], out)

    # Case 1: a mod this profile already has, with its own history.
    target = _controller(tmp_path / "b")
    _make_mod(target, "Alpha")
    target.pd.mod_item("Alpha").completed_count = 2
    mine = datetime(2026, 5, 5)
    target.pd.mod_item("Alpha").date_completed = mine

    target.import_mods([out / f"Alpha{SUFFIX}"])
    md = target.pd.mod_item("Alpha")
    assert md.completed_count == 2, "the local count must win"
    assert md.date_completed == mine

    # Case 2: a mod this profile has never seen — cleared, not inherited.
    fresh = _controller(tmp_path / "c")
    fresh.import_mods([out / f"Alpha{SUFFIX}"])
    assert fresh.pd.mod_item("Alpha").completed_count == 0


def test_importing_something_that_is_not_an_export_reports_it(tmp_path: Path):
    controller = _controller(tmp_path)
    junk = tmp_path / f"broken{SUFFIX}"
    junk.write_bytes(b"not a zip")
    result = controller.import_mods([junk, tmp_path / f"missing{SUFFIX}"])
    assert result["imported"] == []
    assert len(result["failed"]) == 2
    assert "could not be imported" in result["message"]


def test_importable_mods_lists_a_folder(tmp_path: Path):
    controller = _controller(tmp_path)
    _make_mod(controller, "Alpha")
    _make_mod(controller, "Beta")
    out = tmp_path / "out"
    controller.export_mods(["Alpha", "Beta"], out)
    (out / "notes.txt").write_text("ignore me", encoding="utf-8")

    found = controller.importable_mods(out)
    assert sorted(f.mod_name for f in found) == ["Alpha", "Beta"]
    assert controller.importable_mods(tmp_path / "nowhere") == []


# --------------------------------------------------------------------------- #
# The archive came from somewhere else, so it is not trusted
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(os.name == "nt", reason="the escaping member name is POSIX-shaped")
def test_an_archive_cannot_write_outside_the_mod_folder(tmp_path: Path):
    """A zip can name ``../`` or an absolute path, and this one arrived from
    another machine — an import must not be a way to write anywhere on disk."""
    from vaultkeeper.game.mod_transfer import extract

    evil = tmp_path / f"Evil{SUFFIX}"
    with zipfile.ZipFile(evil, "w") as archive:
        archive.writestr(RECORD_NAME, '{"version": 1, "mod": {"mod_name": "Evil"}}')
        archive.writestr("files/../../escaped.txt", "pwned")
        archive.writestr("files/ok.txt", "fine")

    folder = tmp_path / "Profiles" / "P" / "Evil"
    extract(evil, folder)

    assert (folder / "ok.txt").read_text() == "fine"
    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "Profiles" / "escaped.txt").exists()


def test_play_times_from_both_machines_survive_an_import(tmp_path: Path):
    """VB merges the two play-time files rather than replacing one.

    The whole point of carrying a mod to your other machine is to end up with
    both machines' history; a straight file copy would silently discard
    whichever side you imported into.
    """
    from vaultkeeper.core.play_time import PlayTimeInfo

    def record(controller, mod, user, played, when):
        manager = controller._play_data_manager()
        manager.filename = manager.ctx.play_time_file(mod)  # _save_play_times needs it
        manager._save_play_times(
            mod, [PlayTimeInfo(completed=when, play_time=played, user_name=user)]
        )

    source = _controller(tmp_path / "a")
    _make_mod(source, "Alpha")
    record(source, "Alpha", "Desktop", "10 hours 0 mins", "01 Jan 2026")
    out = tmp_path / "carried"
    source.export_mods(["Alpha"], out)

    target = _controller(tmp_path / "b")
    _make_mod(target, "Alpha")
    record(target, "Alpha", "Laptop", "3 hours 0 mins", "02 Feb 2026")

    target.import_mods([out / f"Alpha{SUFFIX}"])

    merged: list = []
    target._play_data_manager().read_play_time_file("Alpha", merged)
    users = {entry.user_name for entry in merged}
    assert users == {"Desktop", "Laptop"}, f"lost a machine's history: {users}"


# --------------------------------------------------------------------------- #
# The menu commands (VB MsExportMods / MsImportMods)
# --------------------------------------------------------------------------- #
def test_the_export_and_import_menu_commands_are_wired(qtbot, tmp_path: Path):
    """Both menu items shipped with the original's icons but no handler.

    A menu entry that looks available and does nothing is worse than one that is
    greyed out, so this pins that they are implemented and enabled.
    """
    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    _make_mod(controller, "Alpha")
    win = MainWindow(controller)
    qtbot.addWidget(win)

    implemented = win.implemented_commands()
    for command in ("MsExportMods", "MsImportMods"):
        action = win.nit_menu.action(command)
        assert action is not None, command
        assert command in implemented, f"{command} has no handler"
        assert action.isEnabled(), f"{command} is greyed out"


def test_exporting_with_nothing_selected_says_so(qtbot, tmp_path, monkeypatch):
    from vaultkeeper.ui import main_window as mw
    from vaultkeeper.ui.main_window import MainWindow

    told = []
    monkeypatch.setattr(
        mw.QMessageBox, "information", lambda _p, _t, text, *a, **k: told.append(text)
    )
    # A file dialog must never open when there is nothing to export.
    monkeypatch.setattr(
        mw.QFileDialog,
        "getExistingDirectory",
        lambda *a, **k: pytest.fail("asked for a folder with no selection"),
    )
    controller = _controller(tmp_path)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_export_mods()
    assert told and "Select the mods" in told[0]
