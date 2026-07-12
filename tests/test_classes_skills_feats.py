"""Tests for the Classes/Skills/Feats reference (VB ClassesSkillsAndFeats)."""

from __future__ import annotations

from functools import cmp_to_key

from vaultkeeper.core.win_sort import win_compare
from vaultkeeper.game.character_reference import (
    default_reference,
    load_class_descriptions,
)

_WIN_KEY = cmp_to_key(win_compare)


# -- Reference data (headless) --------------------------------------------- #
def test_all_classes_sorted_and_described():
    rows = default_reference().all_classes()
    names = [n for n, _ in rows]
    assert "Barbarian" in names
    # Creature/NPC classes (refs 8154/8155) are excluded.
    assert "Commoner" not in names
    # Name-sorted (VB WinCompare natural order).
    assert names == sorted(names, key=_WIN_KEY)
    barb_desc = next(d for n, d in rows if n == "Barbarian")
    assert "Barbarian" in barb_desc


def test_all_skills_have_descriptions():
    rows = default_reference().all_skills()
    assert len(rows) >= 20
    names = [n for n, _ in rows]
    assert names == sorted(names, key=_WIN_KEY)
    assert all(desc for _, desc in rows)


def test_all_feats_exclude_unknown_and_dedup():
    rows = default_reference().all_feats()
    names = [n for n, _ in rows]
    assert names  # non-empty
    assert "Unknown" not in names
    # De-duplicated by name.
    assert len(names) == len(set(names))
    assert names == sorted(names, key=_WIN_KEY)


def test_load_class_descriptions_parses_ref_blocks(tmp_path):
    path = tmp_path / "Class Descriptions.txt"
    path.write_text("]240\nBarbarian text\nmore\n]241\nBard text\n", encoding="latin-1")
    descs = load_class_descriptions(path)
    assert descs[240] == "Barbarian text\nmore"
    assert descs[241] == "Bard text"


# -- Dialog ---------------------------------------------------------------- #
def test_dialog_has_three_populated_tabs(qtbot):
    from vaultkeeper.ui.dialogs.classes_skills_feats import (
        ClassesSkillsAndFeatsDialog,
    )

    dlg = ClassesSkillsAndFeatsDialog()
    qtbot.addWidget(dlg)
    assert dlg.tabs.count() == 3
    assert [dlg.tabs.tabText(i) for i in range(3)] == ["Classes", "Skills", "Feats"]
    classes_tab = dlg.tabs.widget(0)
    assert classes_tab.list.count() > 0
    # The first item's description is shown on load.
    assert classes_tab.description.toPlainText().strip() != ""


def test_dialog_search_filters_list(qtbot):
    from vaultkeeper.ui.dialogs.classes_skills_feats import (
        ClassesSkillsAndFeatsDialog,
    )

    dlg = ClassesSkillsAndFeatsDialog()
    qtbot.addWidget(dlg)
    tab = dlg.tabs.widget(0)  # Classes
    tab.search.setText("bard")
    visible = [
        tab.list.item(i).text()
        for i in range(tab.list.count())
        if not tab.list.item(i).isHidden()
    ]
    assert visible == ["Bard"]
