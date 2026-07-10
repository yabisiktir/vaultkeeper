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
    ExtractType,
    WizardInfo,
    archive_folder_name,
    convert_to_text,
    delete_wizard,
    extract_archives,
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
    from PySide6.QtCore import Qt

    controller = _controller(tmp_path, "Grand Mod")
    (tmp_path / "Profiles" / "P" / "Grand Mod" / WIZARD_FILE).write_text(
        _WIZARD_TEXT, encoding="utf-8"
    )
    dlg = WizardBuilder.show_for(controller, "Grand Mod")
    qtbot.addWidget(dlg)

    assert dlg.title_edit.text() == "My Grand Wizard"
    assert dlg.choices.count() == 2
    assert dlg.choices.item(0).text() == "High Quality Music"
    assert dlg.preferences.count() == 2
    assert dlg.preferences.item(0).checkState() == Qt.CheckState.Checked
    assert dlg.excludes.count() == 1
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


# -- Archive extraction pass (VB ProcessArchive) -------------------------- #


def test_extract_archives_enumerates_contents(tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    mod = tmp_path / "Mod"
    _touch(mod / "pack.7z")  # loose archive -> scanned into result.archives
    scan = _scan(mod)
    assert [a.name for a in scan.archives] == ["pack.7z"]

    extractor = FakeArchiveExtractor(
        contents={
            "pack.7z": {
                "loose.hak": b"x",  # installable top-level file
                "hak/inner.hak": b"x",  # installable file in a sub-folder
                "nested.7z": b"x",  # nested archive -> recursed
                "notes.xyz": b"x",  # unmapped -> skipped
            },
            "nested.7z": {"deep.hak": b"x"},
        }
    )
    mapper = Mapper()
    names = extract_archives(
        scan,
        extractor=extractor,
        is_installable=lambda p: mapper.get_mapped_folder(p, erf_check=True) != "",
    )

    assert set(names) == {"pack.7z", "nested.7z"}
    sf = scan.source_files
    # Top-level installable file, keyed under the archive name.
    assert sf["pack.7z\\loose.hak"] == ExtractType.FOLDER_FILES
    # Sub-folder recorded, and its installable file enumerated.
    assert sf["pack.7z\\hak"] == ExtractType.FOLDERS
    assert sf["pack.7z\\hak\\inner.hak"] == ExtractType.FOLDER_FILES
    # Nested archive recorded as a folder and its contents recursed.
    assert sf["pack.7z\\nested.7z"] == ExtractType.FOLDERS
    assert sf["pack.7z\\nested.7z\\deep.hak"] == ExtractType.FOLDER_FILES
    # Unmapped files are not added.
    assert "pack.7z\\notes.xyz" not in sf


def test_extract_archives_unavailable_backend_is_noop(tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    mod = tmp_path / "Mod"
    _touch(mod / "pack.7z")
    scan = _scan(mod)
    before = dict(scan.source_files)
    names = extract_archives(
        scan,
        extractor=FakeArchiveExtractor(available=False),
        is_installable=lambda p: True,
    )
    assert names == []
    assert scan.source_files == before  # nothing added


def test_is_extracted_file():
    info = WizardInfo(extracted_archives=["pack.7z"])
    assert info.is_extracted_file("pack.7z\\loose.hak") is True
    assert info.is_extracted_file("PACK.7Z\\x") is True  # case-insensitive
    assert info.is_extracted_file("loose.hak") is False  # no parent folder
    assert info.is_extracted_file("other.7z\\x") is False


def test_controller_validate_wizard_extracts_archives(tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller = _controller(tmp_path, "Grand Mod")
    mod = tmp_path / "Profiles" / "P" / "Grand Mod"
    _touch(mod / "pack.7z")
    (mod / WIZARD_FILE).write_text(
        "ExtractArchives\n"
        "SelectMany = P\n"
        "\tpack.7z\\hak\\inner.hak > Inner = Checked\n"
        "\tpack.7z\\hak\\gone.hak > Gone = Checked\n"
        "End SelectMany",
        encoding="utf-8",
    )
    controller._extractor = FakeArchiveExtractor(
        contents={"pack.7z": {"hak/inner.hak": b"x"}}
    )

    result = controller.validate_wizard("Grand Mod")
    assert result["ok"] is True
    # Only the missing archive-inner entry is pruned; the present one survives
    # because the archive was extracted and its contents enumerated.
    assert result["removed"] == 1


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


# -- Authoring: source files + save (VB PopulateFiles + BtSave) ------------ #


def test_wizard_source_files_lists_eligible(tmp_path):
    controller = _controller(tmp_path, "Adv")
    mod = tmp_path / "Profiles" / "P" / "Adv"
    _touch(mod / "a.hak")
    _touch(mod / "sub" / "b.tlk")
    _touch(mod / C.MOD_INSTALLER_DIR / "payload.hak")  # excluded folder
    sources = controller.wizard_source_files("Adv")
    assert "a.hak" in sources
    assert "sub\\b.tlk" in sources
    assert "payload.hak" not in sources


def test_save_wizard_authoring_builds_file(tmp_path):
    controller = _controller(tmp_path, "Adv")
    result = controller.save_wizard_authoring(
        "Adv",
        title="My Wizard",
        select_one_text="Pick one",
        select_many_text="Optional",
        choices=[
            {"key": "hak\\b.hak", "display": "Bravo"},
            {"key": "hak\\a.hak", "display": "Alpha"},
        ],
        preferences=[{"key": "override\\c.tga", "display": "Fancy", "checked": False}],
        excludes=["readme.txt"],
    )
    assert result["ok"]
    info = load_wizard(tmp_path / "Profiles" / "P" / "Adv", "Adv")
    assert info.title == "My Wizard"
    # SelectOne sorted by display name (Alpha before Bravo).
    assert list(info.select_one.values()) == ["Alpha", "Bravo"]
    assert info.select_many[0].checked is False
    assert info.installer_excludes == ["readme.txt"]


def test_dialog_transfer_and_save(qtbot, tmp_path):
    controller = _controller(tmp_path, "Adv")
    mod = tmp_path / "Profiles" / "P" / "Adv"
    _touch(mod / "a.hak")
    _touch(mod / "b.hak")
    dlg = WizardBuilder.show_for(controller, "Adv")
    qtbot.addWidget(dlg)

    # Source list has both files; transfer both into Choices (SelectOne needs >=2).
    assert dlg.source_list.count() == 2
    dlg.source_list.selectAll()
    dlg._add_selected(dlg.choices)
    assert dlg.choices.count() == 2
    assert dlg.source_list.count() == 0  # removed from source

    dlg.title_edit.setText("Authored")
    dlg._on_save()
    info = load_wizard(mod, "Adv")
    assert info is not None
    assert info.title == "Authored"
    assert len(info.select_one) == 2


def test_dialog_add_all_and_remove(qtbot, tmp_path):
    controller = _controller(tmp_path, "Adv")
    mod = tmp_path / "Profiles" / "P" / "Adv"
    _touch(mod / "a.hak")
    _touch(mod / "b.hak")
    dlg = WizardBuilder.show_for(controller, "Adv")
    qtbot.addWidget(dlg)

    dlg._add_all(dlg.excludes)
    assert dlg.excludes.count() == 2
    assert dlg.source_list.count() == 0

    dlg.excludes.selectAll()
    dlg._remove_selected(dlg.excludes)
    assert dlg.excludes.count() == 0
    assert dlg.source_list.count() == 2  # back in source


# -- RunWizard install-time exclusion (VB CreateInstaller.RunWizard) -------- #


def test_resolve_wizard_ignores_select_one():
    from vaultkeeper.game.wizard import resolve_wizard_ignores

    info = parse_wizard_text(
        "SelectOne = Pick\n\thak\\a.hak > A\n\thak\\b.hak > B\nEnd SelectOne", "M"
    )
    # Choosing a.hak ignores the other choice.
    assert resolve_wizard_ignores(info, chosen_one="hak\\a.hak") == ["hak\\b.hak"]


def test_resolve_wizard_ignores_select_many_and_excludes():
    from vaultkeeper.game.wizard import resolve_wizard_ignores

    info = parse_wizard_text(
        "SelectMany = P\n\thak\\x.hak > X = Checked\n\thak\\y.hak > Y = Checked\n"
        "End SelectMany\nInstallerExcludes\n\treadme.txt\nEnd InstallerExcludes",
        "M",
    )
    # Keep only x.hak → y.hak ignored; excludes always ignored.
    ignores = resolve_wizard_ignores(info, checked_many={"hak\\x.hak"})
    assert "hak\\y.hak" in ignores
    assert "readme.txt" in ignores
    assert "hak\\x.hak" not in ignores
    # Cancelling SelectMany (None) ignores every preference.
    all_ignored = resolve_wizard_ignores(info, checked_many=None)
    assert "hak\\x.hak" in all_ignored and "hak\\y.hak" in all_ignored


def test_build_installer_honours_wizard_choice(tmp_path):
    controller = _controller(tmp_path, "Choicey")
    mod = tmp_path / "Profiles" / "P" / "Choicey"
    _touch(mod / "hak" / "music_hi.hak")
    _touch(mod / "hak" / "music_lo.hak")
    (mod / WIZARD_FILE).write_text(
        "SelectOne = Pick\n\thak\\music_hi.hak > Hi\n\thak\\music_lo.hak > Lo\n"
        "End SelectOne",
        encoding="utf-8",
    )
    result = controller.build_installer_payload(
        "Choicey", wizard_choice="hak\\music_hi.hak"
    )
    assert result["ok"]
    installer = mod / C.MOD_INSTALLER_DIR
    # Only the chosen hak is copied; the other is ignored.
    assert list(installer.rglob("music_hi.hak"))
    assert not list(installer.rglob("music_lo.hak"))


def test_wizard_install_prompt(tmp_path):
    controller = _controller(tmp_path, "Choicey", "Plain")
    mod = tmp_path / "Profiles" / "P" / "Choicey"
    (mod / WIZARD_FILE).write_text(
        "SelectOne = Pick\n\ta.hak > A\n\tb.hak > B\nEnd SelectOne", encoding="utf-8"
    )
    prompt = controller.wizard_install_prompt("Choicey")
    assert prompt["run_wizard"] is True
    assert [c["display"] for c in prompt["choices"]] == ["A", "B"]

    # A mod with no wizard reports run_wizard False.
    assert controller.wizard_install_prompt("Plain")["run_wizard"] is False
