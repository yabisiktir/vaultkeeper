"""Tests for the conflicts report + viewer dialog (msconflicts.htm).

The report used to read the *installed* list, so it could only describe files
already on disk: asking an uninstalled mod what it would collide with answered
"nothing". It reads the mod installers now, which is what the topic describes
("depending on the total number of files defined in the Mod Installers").
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.conflicts_viewer import ConflictsViewer


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _add_mod(controller, name, files, *, group="A", installed=False) -> ModData:
    md = ModData(group=group, mod_name=name)
    md.files = [FileKeyInfo.mod_file(group, name, f) for f in files]
    if installed:
        md.mod_state = State.INSTALLED
    controller.pd.add_mod(md)
    return md


def test_report_finds_what_two_installers_both_lay_down(tmp_path):
    controller = _controller(tmp_path)
    _add_mod(controller, "Mod One", ["hak\\cep.hak", "hak\\solo.hak"])
    _add_mod(controller, "Mod Two", ["hak\\cep.hak"], group="B")

    report = controller.conflicts_report()

    assert report["count"] == 1  # solo.hak has one claimant, so it is not one
    row = report["rows"][0]
    assert row["file"] == f"hak{C.FILEKEY_SEPARATOR}cep.hak"
    assert row["mods"] == ["Mod One", "Mod Two"]
    # Priority is Mod List order, so the last one wins.
    assert row["winner"] == "Mod Two"


def test_report_sees_a_mod_that_is_not_installed(tmp_path):
    """The regression this closes: the installed list could not answer this."""
    controller = _controller(tmp_path)
    _add_mod(controller, "Installed One", ["hak\\cep.hak"], installed=True)
    _add_mod(controller, "Not Installed", ["hak\\cep.hak"], group="B")

    assert controller.conflicts_report()["count"] == 1


def test_scopes_cover_what_the_topic_says_they_do(tmp_path):
    controller = _controller(tmp_path)
    _add_mod(controller, "Alpha", ["hak\\shared.hak"], installed=True)
    _add_mod(controller, "Beta", ["hak\\shared.hak"], group="B", installed=True)
    _add_mod(controller, "Gamma", ["hak\\shared.hak"], group="C")

    assert controller.conflicts_report(ProfileController.CONFLICTS_ALL)["mods"] == 3
    installed = controller.conflicts_report(ProfileController.CONFLICTS_INSTALLED)
    assert installed["mods"] == 2
    assert installed["rows"][0]["mods"] == ["Alpha", "Beta"]

    selected = controller.conflicts_report(
        ProfileController.CONFLICTS_SELECTED, ["Beta", "Gamma"]
    )
    assert selected["rows"][0]["mods"] == ["Beta", "Gamma"]
    # One mod cannot conflict with itself.
    assert controller.conflicts_report(
        ProfileController.CONFLICTS_SELECTED, ["Beta"]
    )["count"] == 0


def test_a_mod_listing_the_same_target_twice_is_not_a_conflict(tmp_path):
    controller = _controller(tmp_path)
    md = _add_mod(controller, "Duplicate", ["hak\\same.hak"])
    md.files.append(FileKeyInfo.mod_file("A", "Duplicate", "hak\\same.hak"))

    assert controller.conflicts_report()["count"] == 0


def test_viewer_opens_on_the_selection_and_can_widen_it(qtbot, tmp_path):
    controller = _controller(tmp_path)
    _add_mod(controller, "Alpha", ["hak\\shared.hak"], installed=True)
    _add_mod(controller, "Beta", ["hak\\shared.hak"], group="B", installed=True)
    _add_mod(controller, "Gamma", ["hak\\shared.hak"], group="C")

    dlg = ConflictsViewer.show_for(controller, ["Alpha", "Gamma"])
    qtbot.addWidget(dlg)

    assert dlg.scope_buttons[ProfileController.CONFLICTS_SELECTED].isChecked()
    assert dlg.table.topLevelItem(0).text(1) == "Gamma"  # last selected wins
    assert dlg.table.topLevelItem(0).text(2) == "Alpha"  # others exclude the winner

    dlg.scope_buttons[ProfileController.CONFLICTS_INSTALLED].click()
    assert dlg.table.topLevelItem(0).text(1) == "Beta"
    assert "2 mod(s)" in dlg.summary.text()

    dlg.scope_buttons[ProfileController.CONFLICTS_ALL].click()
    assert dlg.table.topLevelItem(0).text(2) == "Alpha, Beta"


def test_viewer_without_a_selection_offers_no_selected_scope(qtbot, tmp_path):
    controller = _controller(tmp_path)
    _add_mod(controller, "Alpha", ["hak\\shared.hak"])

    dlg = ConflictsViewer.show_for(controller, [])
    qtbot.addWidget(dlg)

    assert not dlg.scope_buttons[ProfileController.CONFLICTS_SELECTED].isEnabled()
    assert dlg.scope_buttons[ProfileController.CONFLICTS_ALL].isChecked()


def test_no_conflicts(qtbot, tmp_path):
    controller = _controller(tmp_path)
    report = controller.conflicts_report()
    assert report["count"] == 0
    dlg = ConflictsViewer.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 0
    assert "No file conflicts" in dlg.summary.text()
