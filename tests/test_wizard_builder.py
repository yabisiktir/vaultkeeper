"""Tests for the Installer Wizard viewer (parser + controller report + dialog).

Covers the VB ``WizardBuilder``/``WizardInfo`` slice: parse a mod's
``.Installer Wizard.nitwiz`` definition into title / extract-archives / SelectOne
choices / SelectMany preferences / InstallerExcludes, expose it via the controller
and render it; plus the authoring core — serialise back (``ConvertToText``),
Save/Delete, and Validate against the mod's real files (``ScanFiles``/``Validate``).
The add/remove-between-lists editing UI and archive-inner validation are deferred.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.core.mapper import Mapper  # noqa: E402
from vaultkeeper.game.wizard import (  # noqa: E402
    WIZARD_FILE,
    archive_folder_name,
    convert_to_text,
    delete_wizard,
    load_wizard,
    parse_wizard_text,
    rewrite_for_publish,
    save_wizard,
    scan_mod_files,
    validate,
)
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.publish_mod import PublishMod  # noqa: E402
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


# -- Serialisation (VB ConvertToText) ------------------------------------- #


def test_convert_to_text_round_trips():
    info = parse_wizard_text(_WIZARD_TEXT, "Grand Mod")
    reparsed = parse_wizard_text(convert_to_text(info), "Grand Mod")
    assert reparsed.title == info.title
    assert reparsed.extract_archives == info.extract_archives
    assert reparsed.select_one == info.select_one
    assert [(p.key, p.display, p.checked) for p in reparsed.select_many] == [
        (p.key, p.display, p.checked) for p in info.select_many
    ]
    assert reparsed.installer_excludes == info.installer_excludes


def test_convert_to_text_omits_single_select_one():
    # VB writes SelectOne only when it has more than one entry.
    info = parse_wizard_text("SelectOne\n\tonly.hak\nEnd SelectOne", "M")
    assert "SelectOne" not in convert_to_text(info)


def test_save_and_load_round_trip(tmp_path):
    info = parse_wizard_text(_WIZARD_TEXT, "Grand Mod")
    assert save_wizard(tmp_path, info) is True
    assert (tmp_path / WIZARD_FILE).is_file()
    loaded = load_wizard(tmp_path, "Grand Mod")
    assert loaded is not None
    assert loaded.select_one == info.select_one


def test_delete_wizard(tmp_path):
    (tmp_path / WIZARD_FILE).write_text(_WIZARD_TEXT, encoding="utf-8")
    assert delete_wizard(tmp_path) is True
    assert not (tmp_path / WIZARD_FILE).exists()
    assert delete_wizard(tmp_path) is False  # already gone


# -- Scan + validate (VB ScanFiles / Validate) ---------------------------- #


def _scan(mod: Path):
    mapper = Mapper()
    return scan_mod_files(
        mod,
        is_installable=lambda p: mapper.get_mapped_folder(p, erf_check=True) != "",
        is_excluded_folder=mapper.is_excluded_folder,
    )


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def test_scan_collects_installable_files_and_archives(tmp_path):
    mod = tmp_path / "Mod"
    _touch(mod / "hak" / "music.hak")  # installable -> "hak\\music.hak"
    _touch(mod / "pack.7z")  # archive -> keyed by name
    _touch(mod / C.PLAY_TIME_FILE)  # reserved -> skipped
    _touch(mod / C.MOD_INSTALLER_DIR / "payload.hak")  # excluded folder -> skipped

    scan = _scan(mod)
    assert scan.suppressed is False
    assert "hak\\music.hak" in scan.source_files
    assert "pack.7z" in scan.source_files
    assert [a.name for a in scan.archives] == ["pack.7z"]
    assert C.PLAY_TIME_FILE not in scan.source_files
    assert "payload.hak" not in scan.source_files


def test_scan_duplicate_name_suppresses(tmp_path):
    mod = tmp_path / "Mod"
    _touch(mod / "hak" / "dup.hak")
    _touch(mod / "override" / "dup.hak")  # same bare name in a different folder
    scan = _scan(mod)
    # get_mapped_folder maps both by extension; keyed by "<folder>\\dup.hak" so the
    # keys differ -> no suppression. Duplicate *archive* names are what suppress.
    assert scan.suppressed is False

    mod2 = tmp_path / "Mod2"
    _touch(mod2 / "a" / "pack.7z")
    _touch(mod2 / "b" / "pack.7z")  # archives keyed by bare name -> collision
    scan2 = _scan(mod2)
    assert scan2.suppressed is True
    assert scan2.duplicate == "pack.7z"


def test_validate_prunes_missing_entries():
    info = parse_wizard_text(
        "SelectOne\n\thak\\here.hak > Here\n\thak\\gone.hak > Gone\nEnd SelectOne\n"
        "InstallerExcludes\n\tmissing.txt\nEnd InstallerExcludes",
        "M",
    )
    source = {"hak\\here.hak": 0}
    removed = validate(info, source)
    assert removed == 2  # gone.hak + missing.txt
    assert list(info.select_one) == ["hak\\here.hak"]
    assert info.installer_excludes == []


# -- Controller authoring ops --------------------------------------------- #


def test_controller_validate_wizard(tmp_path):
    controller = _controller(tmp_path, "Grand Mod")
    mod = tmp_path / "Profiles" / "P" / "Grand Mod"
    _touch(mod / "hak" / "here.hak")  # real file
    (mod / WIZARD_FILE).write_text(
        "SelectOne\n\thak\\here.hak > Here\n\thak\\gone.hak > Gone\nEnd SelectOne",
        encoding="utf-8",
    )

    result = controller.validate_wizard("Grand Mod")
    assert result["ok"] is True
    assert result["removed"] == 1  # gone.hak
    assert result["saved"] is False  # in-memory by default
    # Wizard file unchanged (still lists both) because save was not requested.
    assert "gone.hak" in (mod / WIZARD_FILE).read_text()

    saved = controller.validate_wizard("Grand Mod", save=True)
    assert saved["removed"] == 1
    assert saved["saved"] is True
    assert "gone.hak" not in (mod / WIZARD_FILE).read_text()


def test_controller_delete_wizard(tmp_path):
    controller = _controller(tmp_path, "Grand Mod")
    mod = tmp_path / "Profiles" / "P" / "Grand Mod"
    (mod / WIZARD_FILE).write_text(_WIZARD_TEXT, encoding="utf-8")

    result = controller.delete_wizard("Grand Mod")
    assert result["ok"] is True
    assert not (mod / WIZARD_FILE).exists()
    assert controller.delete_wizard("Grand Mod")["ok"] is False


def test_controller_validate_no_wizard(tmp_path):
    controller = _controller(tmp_path, "Bare Mod")
    result = controller.validate_wizard("Bare Mod")
    assert result["ok"] is True
    assert result["has_wizard"] is False


# -- Dialog authoring buttons --------------------------------------------- #


def test_dialog_validate_button(qtbot, tmp_path):
    controller = _controller(tmp_path, "Grand Mod")
    mod = tmp_path / "Profiles" / "P" / "Grand Mod"
    _touch(mod / "hak" / "here.hak")
    (mod / WIZARD_FILE).write_text(
        "SelectOne\n\thak\\here.hak > Here\n\thak\\gone.hak > Gone\nEnd SelectOne",
        encoding="utf-8",
    )
    dlg = WizardBuilder.show_for(controller, "Grand Mod")
    qtbot.addWidget(dlg)

    assert dlg.validate_button.isEnabled()
    assert dlg.delete_button.isEnabled()
    dlg._on_validate()
    assert "Removed 1" in dlg.summary.text()


def test_dialog_buttons_disabled_without_wizard(qtbot, tmp_path):
    controller = _controller(tmp_path, "Bare Mod")
    dlg = WizardBuilder.show_for(controller, "Bare Mod")
    qtbot.addWidget(dlg)
    assert not dlg.validate_button.isEnabled()
    assert not dlg.delete_button.isEnabled()


# -- Publish rewrite (VB PublishMod wizard update) ------------------------ #


def test_archive_folder_name():
    # Lower-cased, spaces -> "_", apostrophes stripped (VaultArchiveRemoveChars).
    assert archive_folder_name("Baldur's Gate 2.0.7z") == "baldurs_gate_2.0.7z"


def test_rewrite_for_publish_reroots_entries():
    text = (
        "WizardTitle = My Wizard\n"
        "ExtractArchives\n"
        "\n"
        "SelectOne = Pick\n"
        "\thak\\music_hi.hak > High\n"
        "\thak\\music_lo.hak > Low\n"
        "End SelectOne\n"
    )
    out = rewrite_for_publish(text, "coolmod.7z")
    lines = out.splitlines()
    # Title kept; ExtractArchives forced on immediately after it (old one dropped).
    assert lines[0] == "WizardTitle = My Wizard"
    assert lines[1] == "ExtractArchives"
    assert out.count("ExtractArchives") == 1
    # File entries are re-rooted under the archive folder, tab preserved.
    assert "\tcoolmod.7z\\hak\\music_hi.hak > High" in lines
    assert "\tcoolmod.7z\\hak\\music_lo.hak > Low" in lines
    # Block headers/footers untouched.
    assert "SelectOne = Pick" in lines
    assert "End SelectOne" in lines


def test_rewrite_for_publish_strips_existing_archive_prefix():
    text = "SelectOne = P\n\toldmod.7z\\hak\\x.hak > X\nEnd SelectOne\n"
    out = rewrite_for_publish(text, "newmod.7z")
    assert "\tnewmod.7z\\hak\\x.hak > X" in out.splitlines()
    assert "oldmod.7z" not in out


def test_publish_restores_wizard_after_publishing(tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path, "My Mod")
    mod = tmp_path / "Profiles" / "P" / "My Mod"
    original = "SelectOne = P\n\thak\\a.hak > A\n\thak\\b.hak > B\nEnd SelectOne\n"
    (mod / WIZARD_FILE).write_text(original, encoding="utf-8")
    controller._extractor = FakeArchiveExtractor()

    result = controller.publish_mod("My Mod")
    assert result["ok"]
    # The wizard file on disk is restored to its original content after publishing.
    assert (mod / WIZARD_FILE).read_text() == original


# -- Publish dialog ------------------------------------------------------- #


def test_publish_dialog_live_name_and_publish(qtbot, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.core import constants as C
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path, "My Mod")
    controller._extractor = FakeArchiveExtractor()

    dlg = PublishMod.show_for(controller, "My Mod")
    qtbot.addWidget(dlg)
    assert dlg.archive_label.text() == "My Mod.7z"
    dlg.version_edit.setText("2.0")
    assert dlg.archive_label.text() == "My Mod 2.0.7z"
    assert not dlg.guide_check.isEnabled()  # deferred

    import unittest.mock as mock

    with mock.patch.object(QMessageBox, "information"):
        dlg._on_publish()
    published = (
        controller.ctx.profile_mods_dir / "My Mod" / C.PUBLISHED_DIR / "My Mod 2.0.7z"
    )
    assert controller._extractor.create_calls[0][0] == published


def test_dialog_delete_button(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    controller = _controller(tmp_path, "Grand Mod")
    mod = tmp_path / "Profiles" / "P" / "Grand Mod"
    (mod / WIZARD_FILE).write_text(_WIZARD_TEXT, encoding="utf-8")
    dlg = WizardBuilder.show_for(controller, "Grand Mod")
    qtbot.addWidget(dlg)

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    dlg._on_delete()
    assert not (mod / WIZARD_FILE).exists()
    assert not dlg.delete_button.isEnabled()  # refresh disabled it
