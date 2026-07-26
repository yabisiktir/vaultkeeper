"""Tests for the Character Viewer dialog + controller character/portrait methods."""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.core.formats.bic_reader import (  # noqa: E402
    CharacterClass,
    CharacterInfo,
    Gender,
    Race,
)
from vaultkeeper.game.character import CharacterFile  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.character_viewer import (  # noqa: E402
    CharacterViewer,
    tga_to_pixmap,
)


def _char(
    name: str,
    path: Path,
    *,
    valid: bool = True,
    resref: str = "hero_",
    feat_ids: list[int] | None = None,
    skill_ranks: list[int] | None = None,
) -> CharacterFile:
    info = CharacterInfo(
        name=name,
        gender=Gender.MALE,
        race_id=Race.HUMAN.value,
        classes=[(CharacterClass.BARD.value, 5)],
        level=5,
        experience=10_000,
        alignment_good_evil=50,
        alignment_lawful_chaotic=50,
        hit_points=40,
        portrait_resref=resref,
        feat_ids=feat_ids or [],
        skill_ranks=skill_ranks or [],
        is_valid=valid,
    )
    return CharacterFile(path=path, info=info)


def _write_tga(path: Path, w: int = 2, h: int = 2) -> None:
    """A tiny uncompressed 24-bit BGR TGA the reader can decode."""
    header = struct.pack(
        "<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 24, 0
    )
    pixels = bytes([0, 0, 255] * (w * h))  # BGR red
    path.write_bytes(header + pixels)


def test_copy_details_and_level_to_clipboard(qtbot, tmp_path):
    from PySide6.QtWidgets import QApplication

    dlg = CharacterViewer([_char("Alpha Hero", tmp_path / "a.bic")], None)
    qtbot.addWidget(dlg)
    dlg._list.setCurrentRow(0)

    dlg._on_copy_details()
    assert "Alpha Hero" in QApplication.clipboard().text()

    dlg._on_copy_level()
    level = QApplication.clipboard().text()
    assert level.startswith("Alpha Hero:")
    assert "Bard 5" in level  # class/level line


def test_viewer_populates_list_and_summary(qtbot, tmp_path):
    chars = [
        _char("Alpha Hero", tmp_path / "a.bic"),
        _char("Beta Hero", tmp_path / "b.bic"),
    ]
    dlg = CharacterViewer(chars, None)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 2
    # Title carries the file count (VB "Character Explorer — N files shown").
    assert dlg.windowTitle() == "Character Explorer — 2 files shown"
    # First is auto-selected; its summary shows.
    assert "Alpha Hero" in dlg._summary.toPlainText()
    dlg._list.setCurrentRow(1)
    assert "Beta Hero" in dlg._summary.toPlainText()


def test_viewer_empty_state(qtbot):
    dlg = CharacterViewer([], None)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 0
    assert "No character files" in dlg._summary.toPlainText()


def test_viewer_has_help_button(qtbot, tmp_path):
    # VB CharacterViewer has a Help button → HelpFile.Open("MsCharacterViewer").
    from PySide6.QtWidgets import QPushButton

    dlg = CharacterViewer([_char("Hero", tmp_path / "h.bic")], None)
    qtbot.addWidget(dlg)
    help_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Help")
    help_btn.click()
    assert "mscharacterviewer.htm" in dlg._help_viewer.browser.source().toString().lower()


def test_viewer_populates_skills_and_feats(qtbot, tmp_path):
    # feat 0 = Alertness, feat 1 = Ambidexterity (bundled table); skills by id.
    chars = [
        _char(
            "Feat Hero",
            tmp_path / "f.bic",
            feat_ids=[1, 0],
            skill_ranks=[0, 12],  # Animal Empathy 0, Concentration 12
        )
    ]
    dlg = CharacterViewer(chars, None)
    qtbot.addWidget(dlg)

    # Skills tab: name-sorted rows with ranks + description on selection.
    assert dlg._skills.topLevelItemCount() == 2
    skill_names = [
        dlg._skills.topLevelItem(i).text(0)
        for i in range(dlg._skills.topLevelItemCount())
    ]
    assert skill_names == ["Animal Empathy", "Concentration"]
    dlg._skills.setCurrentItem(dlg._skills.topLevelItem(1))
    assert dlg._skills.topLevelItem(1).text(1) == "12"
    assert dlg._skill_desc.toPlainText()  # Concentration description shows

    # Feats tab: named, deduped, sorted; description shows on selection.
    feat_names = [dlg._feats.item(i).text() for i in range(dlg._feats.count())]
    assert feat_names == ["Alertness", "Ambidexterity"]
    dlg._feats.setCurrentRow(0)
    assert dlg._feat_desc.toPlainText()


def test_viewer_switches_character_clears_skills(qtbot, tmp_path):
    chars = [
        _char("With Feats", tmp_path / "a.bic", feat_ids=[0], skill_ranks=[3]),
        _char("No Feats", tmp_path / "b.bic"),
    ]
    dlg = CharacterViewer(chars, None)
    qtbot.addWidget(dlg)
    assert dlg._feats.count() == 1
    dlg._list.setCurrentRow(1)
    assert dlg._feats.count() == 0
    assert dlg._skills.topLevelItemCount() == 0


def test_viewer_shows_portrait_when_resolvable(qtbot, tmp_path):
    portraits = tmp_path / "portraits"
    portraits.mkdir()
    _write_tga(portraits / "hero_m.tga")

    def resolver(resref, own_folder):
        from vaultkeeper.game.character import resolve_portrait

        return resolve_portrait(resref, [portraits])

    dlg = CharacterViewer([_char("Hero", tmp_path / "h.bic")], resolver)
    qtbot.addWidget(dlg)
    # A portrait pixmap was loaded and displayed.
    assert dlg._portrait.pixmap() is not None
    assert not dlg._portrait.pixmap().isNull()


def test_tga_to_pixmap_reads_real_tga(tmp_path):
    _write_tga(tmp_path / "p.tga", 4, 4)
    pix = tga_to_pixmap(tmp_path / "p.tga")
    assert pix is not None and not pix.isNull()


def test_tga_to_pixmap_missing_file(tmp_path):
    assert tga_to_pixmap(tmp_path / "nope.tga") is None


# -- Controller character/portrait plumbing ------------------------------------ #
def test_controller_character_files_scans_vault_and_saves(tmp_path, monkeypatch):
    user = tmp_path / "gameuser"
    (user / "localvault").mkdir(parents=True)
    (user / "saves" / "000 - quicksave").mkdir(parents=True)
    # Non-bic files are ignored; we only assert the scan wiring runs without error.
    (user / "localvault" / "notes.txt").write_bytes(b"x")

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.ctx.game_user_dir = user
    assert controller.character_files() == []  # no .bic present, but no crash

    dirs = controller.portrait_search_dirs()
    assert user / "override" in dirs
    assert user / "portraits" in dirs


# -- Portrait Manager ---------------------------------------------------------- #
class _FakePortraitController:
    def __init__(self, portraits):
        self._portraits = portraits

    def installed_portraits_report(self):
        return {"portraits": self._portraits, "count": len(self._portraits)}


def test_portrait_manager_lists_and_previews(qtbot, tmp_path):
    from vaultkeeper.game.character import PORTRAIT_SIZES
    from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager

    sizes = {}
    for size in PORTRAIT_SIZES:  # a full five-size set on disk
        path = tmp_path / f"po_hero{size}.tga"
        _write_tga(path, 8, 8)
        sizes[size] = path
    portraits = [{"resref": "po_hero", "mod": "Heroes", "group": "", "sizes": sizes}]
    dlg = PortraitManager(_FakePortraitController(portraits))
    qtbot.addWidget(dlg)
    assert dlg._tree.topLevelItemCount() == 1
    # Title carries the count (VB "Portrait Manager — Installed Portraits: N").
    assert dlg.windowTitle() == "Portrait Manager — Installed Portraits: 1"
    # All five size thumbnails loaded for the selected portrait.
    for size in PORTRAIT_SIZES:
        pixmap = dlg._thumbs[size].pixmap()
        assert pixmap is not None and not pixmap.isNull()


def test_portrait_manager_empty(qtbot):
    from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager

    dlg = PortraitManager(_FakePortraitController([]))
    qtbot.addWidget(dlg)
    assert dlg._tree.topLevelItemCount() == 0


def test_portrait_manager_extract_from_hak(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager

    calls = {"extracted": None}

    class _Ctl:
        def installed_portraits_report(self):
            return {"portraits": [], "count": 0}

        def extract_hak_portraits(self, hak):
            calls["extracted"] = hak
            return {"count": 5, "message": "Extracted 5 portrait(s)."}

    dlg = PortraitManager(_Ctl())
    qtbot.addWidget(dlg)
    assert dlg._extract_button.isEnabled()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: ("/haks/faces.hak", "")
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg._on_extract()
    assert str(calls["extracted"]) == "/haks/faces.hak"


def test_viewer_name_search_filters(qtbot, tmp_path):
    chars = [
        _char("Alpha Hero", tmp_path / "a.bic"),
        _char("Beta Knight", tmp_path / "b.bic"),
        _char("Gamma Hero", tmp_path / "c.bic"),
    ]
    dlg = CharacterViewer(chars, None)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 3
    # Typing filters the list case-insensitively by name.
    dlg._search.setText("hero")
    assert dlg._list.count() == 2
    names = [dlg._list.item(i).text() for i in range(dlg._list.count())]
    assert all("Hero" in n for n in names)
    assert "2 of 3 shown" in dlg._count_label.text()
    # Clearing restores the full list.
    dlg._search.setText("")
    assert dlg._list.count() == 3


# -- Level/class filter (VB CharacterFilter) ----------------------------------- #
def _leveled_char(name, path, level, classes=None):
    info = CharacterInfo(
        name=name,
        gender=Gender.MALE,
        race_id=Race.HUMAN.value,
        classes=classes or [(CharacterClass.BARD.value, level)],
        level=level,
        experience=10_000,
        alignment_good_evil=50,
        alignment_lawful_chaotic=50,
        hit_points=40,
        portrait_resref="hero_",
        feat_ids=[],
        skill_ranks=[],
        is_valid=True,
    )
    return CharacterFile(path=path, info=info)


def test_viewer_level_filter_applies(qtbot, tmp_path):
    from vaultkeeper.game.character_filter import CharacterLevelFilter

    chars = [
        _leveled_char("Low", tmp_path / "a.bic", 5),
        _leveled_char("Mid", tmp_path / "b.bic", 20),
        _leveled_char("High", tmp_path / "c.bic", 40),
    ]
    dlg = CharacterViewer(chars, None)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 3
    # "=20" keeps only the level-20 character; title + count reflect the filter.
    dlg._filter = CharacterLevelFilter.parse("=20")
    dlg._populate_list()
    assert dlg._list.count() == 1
    assert "Mid" in dlg._list.item(0).text()
    assert "1 of 3 shown" in dlg._count_label.text()
    assert "1 of 3 files shown" in dlg.windowTitle()


def test_viewer_class_filter_applies(qtbot, tmp_path):
    from vaultkeeper.game.character_filter import CharacterLevelFilter

    chars = [
        _leveled_char("Barder", tmp_path / "a.bic", 10, [(CharacterClass.BARD.value, 10)]),
        _leveled_char("Wizzy", tmp_path / "b.bic", 10, [(CharacterClass.WIZARD.value, 10)]),
    ]
    dlg = CharacterViewer(chars, None)
    qtbot.addWidget(dlg)
    dlg._filter = CharacterLevelFilter.parse("1", ["Bard"])
    dlg._populate_list()
    assert dlg._list.count() == 1
    assert "Barder" in dlg._list.item(0).text()


def test_viewer_filter_button_opens_dialog_and_applies(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from vaultkeeper.ui.dialogs import character_filter as cf_mod

    chars = [
        _leveled_char("Low", tmp_path / "a.bic", 5),
        _leveled_char("High", tmp_path / "b.bic", 30),
    ]
    dlg = CharacterViewer(chars, None)
    qtbot.addWidget(dlg)
    assert dlg._filter_btn.text() == "Show all Levels"

    # Simulate the modal filter dialog returning ">=25".
    def fake_exec(self):
        self._level.setText("25")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(cf_mod.CharacterFilter, "exec", fake_exec)
    dlg._on_filter()
    assert dlg._list.count() == 1
    assert "High" in dlg._list.item(0).text()
    assert dlg._filter_btn.text() == "Show Level 25 and higher"


# -- CharacterFilter dialog (VB CharacterFilter) ------------------------------- #
def test_character_filter_dialog_validation_blocks_accept(qtbot):
    from PySide6.QtWidgets import QDialog

    from vaultkeeper.ui.dialogs.character_filter import CharacterFilter

    accepted = QDialog.DialogCode.Accepted
    dlg = CharacterFilter(["Bard", "Cleric", "Wizard"], level_text="99")
    qtbot.addWidget(dlg)
    dlg._on_apply()  # 99 is out of range -> stays open, shows the error
    assert dlg.result() != accepted
    assert "between 1 and 40" in dlg._status.text()
    dlg._level.setText("=20")
    dlg._on_apply()
    assert dlg.result() == accepted
    assert dlg.level_text == "=20"


def test_character_filter_dialog_caps_three_classes(qtbot):
    from PySide6.QtCore import Qt

    from vaultkeeper.game.character_filter import CLASS_NAME_ERROR
    from vaultkeeper.ui.dialogs.character_filter import CharacterFilter

    names = ["Bard", "Cleric", "Druid", "Fighter"]
    dlg = CharacterFilter(names)
    qtbot.addWidget(dlg)
    for row in range(4):
        dlg._classes.item(row).setCheckState(Qt.CheckState.Checked)
    # Only the first three ticks are honoured; the fourth is refused.
    assert dlg.class_names == ("Bard", "Cleric", "Druid")
    assert dlg._status.text() == CLASS_NAME_ERROR
    assert dlg._classes.item(3).checkState() == Qt.CheckState.Unchecked


def test_character_filter_dialog_reset(qtbot):
    from PySide6.QtCore import Qt

    from vaultkeeper.ui.dialogs.character_filter import CharacterFilter

    dlg = CharacterFilter(["Bard", "Cleric"], level_text="20", checked_classes=("Bard",))
    qtbot.addWidget(dlg)
    assert dlg.class_names == ("Bard",)
    dlg._on_reset()
    assert dlg._level.text() == "1"
    assert dlg.class_names == ()
    assert dlg._classes.item(0).checkState() == Qt.CheckState.Unchecked
