"""Validate Neverwinter Nights (VB MsValidate / validatedatabase.htm).

The game-side twin of Remove Illegal Mod Files: the same question asked of the
installation and user-files folders rather than of a mod's installer payload.
Report first, delete only if asked — these are files in the *game*, and some of
them will be somebody's deliberate additions.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.ui.controller import ProfileController


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    # On EE the mapped folders are in the *user files* dir, not the install —
    # which is where anything the game reads actually sits.
    user = tmp_path / "user"
    for folder in ("hak", "tlk", "override"):
        (user / folder).mkdir(parents=True)
    (user / "hak" / "good.hak").write_bytes(b"x")
    # .txt and .ini are legal NWN extensions; .doc and .pdf are not.
    (user / "hak" / "notes.txt").write_bytes(b"x" * 10)
    (user / "hak" / "manual.doc").write_bytes(b"x" * 10)
    (user / "override" / "readme.pdf").write_bytes(b"x" * 20)
    (user / "tlk" / "dialog.tlk").write_bytes(b"x")

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=user,
    )


def test_it_finds_files_the_game_has_no_use_for(controller):
    report = controller.validate_neverwinter_nights()
    found = {(r["folder"], r["filename"]) for r in report["rows"]}
    assert ("hak", "manual.doc") in found
    assert ("override", "readme.pdf") in found
    assert not any(r["filename"] == "good.hak" for r in report["rows"])
    assert not any(r["filename"] == "dialog.tlk" for r in report["rows"])
    assert not any(r["filename"] == "notes.txt" for r in report["rows"]), (
        ".txt is a legal NWN extension — readmes live beside haks quite properly"
    )


def test_the_report_counts_what_it_looked_at(controller):
    report = controller.validate_neverwinter_nights()
    assert report["scanned"] >= 5
    assert report["count"] == len(report["rows"]) == 2
    assert "do not belong" in report["message"]


def test_a_clean_installation_says_so(tmp_path):
    user = tmp_path / "user"
    (user / "hak").mkdir(parents=True)
    (user / "hak" / "fine.hak").write_bytes(b"x")
    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=user,
    )
    report = c.validate_neverwinter_nights()
    assert report["count"] == 0
    assert "Nothing is out of place" in report["message"]


def test_nothing_is_deleted_by_looking(controller):
    controller.validate_neverwinter_nights()
    assert (controller.ctx.game_user_dir / "hak" / "manual.doc").exists()


def test_deleting_removes_them_and_rescans(controller):
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.recycle_on_delete = False
    save_settings(settings)

    report = controller.validate_neverwinter_nights()
    result = controller.delete_illegal_game_files([r["path"] for r in report["rows"]])

    assert result["ok"] and result["removed"] == 2
    assert "permanently" in result["message"]
    assert not (controller.ctx.game_user_dir / "hak" / "manual.doc").exists()
    assert (controller.ctx.game_user_dir / "hak" / "good.hak").exists()
    assert (controller.ctx.game_user_dir / "hak" / "notes.txt").exists()
    assert controller.validate_neverwinter_nights()["count"] == 0


def test_the_command_is_live(qtbot, controller):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert "MsValidate" in win.implemented_commands()
    assert win.nit_menu.action("MsValidate").isEnabled()


# -- The dialog: nothing goes without being ticked ----------------------------- #
def test_nothing_is_ticked_to_start_with(qtbot, controller):
    """Against a real installation every finding was legitimate — PRC's .hif
    files and the game's own repository.json — so VB's delete-the-whole-list
    button would have been actively harmful here."""
    from PySide6.QtCore import Qt

    from vaultkeeper.ui.dialogs.validate_nwn import ValidateNwnDialog

    dlg = ValidateNwnDialog.show_for(controller)
    qtbot.addWidget(dlg)

    assert dlg.table.topLevelItemCount() == 2
    states = {
        dlg.table.topLevelItem(i).checkState(0)
        for i in range(dlg.table.topLevelItemCount())
    }
    assert states == {Qt.CheckState.Unchecked}
    assert not dlg.delete_button.isEnabled(), "nothing ticked, nothing to do"


def test_deleting_takes_only_the_ticked_ones(qtbot, controller, monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.ui.dialogs.validate_nwn import ValidateNwnDialog

    settings = load_settings()
    settings.recycle_on_delete = False
    save_settings(settings)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )

    dlg = ValidateNwnDialog.show_for(controller)
    qtbot.addWidget(dlg)
    for i in range(dlg.table.topLevelItemCount()):
        item = dlg.table.topLevelItem(i)
        if item.text(0) == "manual.doc":
            item.setCheckState(0, Qt.CheckState.Checked)

    assert dlg.delete_button.isEnabled()
    dlg._on_delete()

    user = controller.ctx.game_user_dir
    assert not (user / "hak" / "manual.doc").exists()
    assert (user / "override" / "readme.pdf").exists(), "not ticked, not touched"
    assert dlg.table.topLevelItemCount() == 1
