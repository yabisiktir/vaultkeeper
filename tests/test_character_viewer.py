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
        race=Race.HUMAN,
        classes=[(CharacterClass.BARD, 5)],
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


def test_viewer_populates_list_and_summary(qtbot, tmp_path):
    chars = [
        _char("Alpha Hero", tmp_path / "a.bic"),
        _char("Beta Hero", tmp_path / "b.bic"),
    ]
    dlg = CharacterViewer(chars, None)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 2
    # First is auto-selected; its summary shows.
    assert "Alpha Hero" in dlg._summary.toPlainText()
    dlg._list.setCurrentRow(1)
    assert "Beta Hero" in dlg._summary.toPlainText()


def test_viewer_empty_state(qtbot):
    dlg = CharacterViewer([], None)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 0
    assert "No character files" in dlg._summary.toPlainText()


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
def test_portrait_manager_lists_and_previews(qtbot, tmp_path):
    from vaultkeeper.game.character import scan_portraits
    from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager

    for size in ("m", "h"):
        _write_tga(tmp_path / f"po_hero_{size}.tga", 8, 8)
    entries = scan_portraits([tmp_path])
    dlg = PortraitManager(entries)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 1
    # Both previews loaded for the selected portrait.
    assert dlg._huge.pixmap() is not None and not dlg._huge.pixmap().isNull()
    assert dlg._medium.pixmap() is not None and not dlg._medium.pixmap().isNull()


def test_portrait_manager_empty(qtbot):
    from vaultkeeper.ui.dialogs.portrait_manager import PortraitManager

    dlg = PortraitManager([])
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 0
