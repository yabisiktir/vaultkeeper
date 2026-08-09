"""New Folder / New Text File / New RTF File, Refresh Workshop Files, and
Send Diagnostic Information — four menu items that existed and did nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    payload = tmp_path / "Profiles" / "P" / "Swordflight" / C.MOD_INSTALLER_DIR / "hak"
    payload.mkdir(parents=True)
    (payload / "sf.hak").write_bytes(b"x")
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=tmp_path / "user",
    )


def _payload(controller: ProfileController) -> Path:
    return controller.ctx.profile_mods_dir / "Swordflight" / C.MOD_INSTALLER_DIR


# -- New folder ----------------------------------------------------------------- #
def test_a_new_folder_appears_in_the_payload(controller):
    result = controller.create_mod_folder("Swordflight", "music")
    assert result["ok"]
    assert (_payload(controller) / "music").is_dir()


def test_an_existing_folder_is_not_silently_reused(controller):
    controller.create_mod_folder("Swordflight", "music")
    again = controller.create_mod_folder("Swordflight", "music")
    assert not again["ok"] and "already there" in again["message"]


@pytest.mark.parametrize("name", ["", "   ", "a/b", "a:b", "a*b"])
def test_a_name_that_is_not_a_folder_name_is_refused(controller, name):
    assert controller.create_mod_folder("Swordflight", name)["ok"] is False


# -- New file ------------------------------------------------------------------- #
def test_a_new_file_is_part_of_the_installer_immediately(controller):
    """Not after the next rescan: a file you have to go and find is a file you
    will forget you made."""
    result = controller.create_mod_file("Swordflight", "hak", "Readme.txt")

    assert result["ok"]
    assert (_payload(controller) / "hak" / "Readme.txt").is_file()
    md = controller.pd.mod_item("Swordflight")
    assert ("hak", "Readme.txt") in {(fk.folder, fk.filename) for fk in md.files}


def test_a_file_can_be_made_in_a_folder_that_does_not_exist_yet(controller):
    assert controller.create_mod_file("Swordflight", "docs", "Notes.rtf")["ok"]
    assert (_payload(controller) / "docs" / "Notes.rtf").is_file()


def test_an_existing_file_is_never_overwritten(controller):
    (_payload(controller) / "hak" / "Readme.txt").write_text("mine")
    result = controller.create_mod_file("Swordflight", "hak", "Readme.txt")
    assert not result["ok"]
    assert (_payload(controller) / "hak" / "Readme.txt").read_text() == "mine"


def test_the_commands_are_live(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    impl = win.implemented_commands()
    for cid in ("MsNewFolder", "MsNewTextFile", "MsNewRtfFile",
                "MsRefreshWorkshopFiles", "MsSendDiagInfo"):
        assert cid in impl, cid
        assert win.nit_menu.action(cid).isEnabled(), cid


def test_new_folder_on_the_mod_list_means_new_mod(qtbot, controller, monkeypatch):
    """VB routes it that way, and it is right: a new "folder" in the mod list is
    a new mod."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.show()
    win._tree.setFocus()

    called: list[int] = []
    monkeypatch.setattr(win, "_on_new_mod", lambda: called.append(1))
    win._on_new_contents_folder()
    assert called == [1]


# -- Diagnostics ---------------------------------------------------------------- #
def test_the_diagnostic_report_carries_what_a_bug_report_needs(controller):
    report = controller.diagnostic_report()
    text = report["text"]
    for expected in ("Vaultkeeper", "Paths", "Profile", "game install:", "mods:"):
        assert expected in text, expected
    assert Path(report["path"]).is_file(), "written out as well as returned"


def test_the_report_is_readable_before_it_is_shared(controller):
    """It names folders, and a home directory has somebody's name in it — so it
    is shown, not posted."""
    report = controller.diagnostic_report()
    assert str(controller.ctx.game_root) in report["text"]


def test_a_missing_log_does_not_stop_the_report(controller, monkeypatch):
    monkeypatch.setattr(controller, "nit_log_path", lambda: Path("/nowhere/nit.log"))
    report = controller.diagnostic_report()
    assert "could not be read" in report["text"] or "(empty)" in report["text"]


# -- Workshop refresh ------------------------------------------------------------ #
def test_refreshing_workshop_files_on_a_non_steam_install(controller):
    diff = controller.workshop_refresh()
    assert diff["summary"] == "This is not a Steam install."


# -- Remembering where the notes were left (newtopic67 / MsClearScrollInfo) ------ #
def test_the_notes_come_back_where_they_were_left(qtbot, controller):
    """A mod's notes can be pages long; returning to the top every time is the
    sort of small thing that makes a tool tiring."""
    from vaultkeeper.core.mod_data import ModData

    controller.pd.add_mod(ModData(group="Adv", mod_name="Other"))
    controller.save_notes("Swordflight", "line\n" * 200)

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Swordflight")

    cursor = win._details.textCursor()
    cursor.setPosition(400)
    win._details.setTextCursor(cursor)

    win._select_mod_by_name("Other")
    win._select_mod_by_name("Swordflight")

    assert win._details.textCursor().position() == 400


def test_a_position_past_the_end_does_not_break_it(qtbot, controller):
    """The notes may have been shortened since — clamp rather than throw."""
    controller.save_notes("Swordflight", "short")
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._notes_positions["Swordflight"] = 9_999

    win._select_mod_by_name("Swordflight")
    assert win._details.textCursor().position() == len("short")


def test_clearing_forgets_them_and_can_turn_it_off(qtbot, controller, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.notes_positions = {"Swordflight": 120}
    settings.remember_text_positions = True
    save_settings(settings)

    win = MainWindow(controller)
    qtbot.addWidget(win)

    def fake_exec(self) -> int:
        self.checkBox().setChecked(False)  # "stop remembering"
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    win._on_clear_text_positions()

    after = load_settings()
    assert after.notes_positions == {}
    assert after.remember_text_positions is False
    assert win._notes_positions == {}


def test_nothing_is_remembered_when_it_is_turned_off(qtbot, controller):
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.remember_text_positions = False
    settings.notes_positions = {}
    save_settings(settings)

    controller.save_notes("Swordflight", "line\n" * 50)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Swordflight")
    cursor = win._details.textCursor()
    cursor.setPosition(100)
    win._details.setTextCursor(cursor)

    win._remember_notes_position()
    assert win._notes_positions == {}
