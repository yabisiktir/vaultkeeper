"""Tests for the Installer Wizard viewer (parser + controller report + dialog).

Covers the bounded VB ``WizardBuilder``/``WizardInfo`` slice: parse a mod's
``.Installer Wizard.nitwiz`` definition into title / extract-archives / SelectOne
choices / SelectMany preferences / InstallerExcludes, expose it via the controller
and render it. The authoring (Save/Delete/validate) action is deferred.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.game.wizard import (  # noqa: E402
    WIZARD_FILE,
    load_wizard,
    parse_wizard_text,
)
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.wizard_builder import WizardBuilder  # noqa: E402

_WIZARD_TEXT = """\
' a comment line
WizardTitle = My Grand Wizard
ExtractArchives

SelectOne = Pick your music pack
\thak\\music_hi.hak > High Quality Music
\thak\\music_lo.hak > Low Quality Music
End SelectOne

SelectMany = Optional extras
\toverride\\hires.tga > Hi-Res Textures = Checked
\toverride\\altfont_v2.tlk
End SelectMany

InstallerExcludes
\treadme.txt
End InstallerExcludes
"""


# -- Parser (VB WizardInfo.Load) ------------------------------------------ #


def test_parse_full_wizard():
    info = parse_wizard_text(_WIZARD_TEXT, "Grand Mod")
    assert info.title == "My Grand Wizard"
    assert info.extract_archives is True
    assert info.select_one_text == "Pick your music pack"
    assert info.select_one == {
        "hak\\music_hi.hak": "High Quality Music",
        "hak\\music_lo.hak": "Low Quality Music",
    }
    assert info.select_many_text == "Optional extras"
    assert [(p.key, p.display, p.checked) for p in info.select_many] == [
        ("override\\hires.tga", "Hi-Res Textures", True),
        # No ">" and no "=": display name derived from the file stem.
        ("override\\altfont_v2.tlk", "Altfont V2", False),
    ]
    assert info.installer_excludes == ["readme.txt"]
    assert info.run_wizard is True


def test_parse_defaults_when_blank():
    info = parse_wizard_text("", "Some Mod")
    assert info.title == "Some Mod Installer Wizard"  # default from mod name
    assert info.select_one_text == "Choose which file you want to use."
    assert info.select_many_text == "Select which files, if any, you want to use."
    assert info.run_wizard is False  # nothing to present


def test_parse_is_case_insensitive_for_keywords():
    info = parse_wizard_text("selectone\n\ta.txt\nend selectone", "M")
    assert "a.txt" in info.select_one


def test_load_missing_returns_none(tmp_path):
    assert load_wizard(tmp_path, "Ghost") is None


def test_load_reads_file(tmp_path):
    (tmp_path / WIZARD_FILE).write_text(_WIZARD_TEXT, encoding="utf-8")
    info = load_wizard(tmp_path, "Grand Mod")
    assert info is not None
    assert info.extract_archives is True
    assert len(info.select_one) == 2


# -- Controller report ---------------------------------------------------- #


def _controller(tmp_path: Path, *mods: str) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    for name in mods:
        (profile_mods / name / C.MOD_INSTALLER_DIR).mkdir(parents=True)
    game_root = tmp_path / "steamapps" / "common" / "Neverwinter Nights"
    game_root.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
    )


def test_report_reads_mod_wizard(tmp_path):
    controller = _controller(tmp_path, "Grand Mod")
    (tmp_path / "Profiles" / "P" / "Grand Mod" / WIZARD_FILE).write_text(
        _WIZARD_TEXT, encoding="utf-8"
    )
    report = controller.wizard_report("Grand Mod")
    assert report["has_wizard"] is True
    assert report["title"] == "My Grand Wizard"
    assert report["extract_archives"] is True
    assert [c["display"] for c in report["choices"]] == [
        "High Quality Music",
        "Low Quality Music",
    ]
    assert report["preferences"][0] == {
        "key": "override\\hires.tga",
        "display": "Hi-Res Textures",
        "checked": True,
    }
    assert report["excludes"] == ["readme.txt"]
    assert report["summary"] == "Choices: 2. Preferences: 2. Installer excludes: 1."


def test_report_no_wizard(tmp_path):
    controller = _controller(tmp_path, "Bare Mod")
    report = controller.wizard_report("Bare Mod")
    assert report["has_wizard"] is False
    assert report["choices"] == []
    assert report["summary"] == "No installer wizard defined for Bare Mod."


# -- Dialog --------------------------------------------------------------- #


def test_dialog_populates_lists(qtbot, tmp_path):
    controller = _controller(tmp_path, "Grand Mod")
    (tmp_path / "Profiles" / "P" / "Grand Mod" / WIZARD_FILE).write_text(
        _WIZARD_TEXT, encoding="utf-8"
    )
    dlg = WizardBuilder.show_for(controller, "Grand Mod")
    qtbot.addWidget(dlg)

    assert dlg.title_label.text() == "My Grand Wizard"
    assert dlg.extract_label.text() == "Yes"
    assert dlg.choices.topLevelItemCount() == 2
    assert dlg.choices.topLevelItem(0).text(0) == "High Quality Music"
    assert dlg.preferences.topLevelItemCount() == 2
    assert "on" in dlg.preferences.topLevelItem(0).text(0)
    assert dlg.excludes.topLevelItemCount() == 1
    assert "Choices: 2" in dlg.summary.text()
