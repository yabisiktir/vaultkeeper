"""Tests for the mod-explorer report + dialog."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.mod_data import ModData, Ratings
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.mod_explorer import ModExplorer


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.pd.add_mod(
        ModData(group="Adv", mod_name="Swordflight", rating=Ratings.EXCELLENT, completed_count=2)
    )
    controller.pd.add_mod(ModData(group="Adv", mod_name="Abyss"))
    return controller


def test_mod_explorer_report(qtbot, tmp_path):
    report = _controller(tmp_path).mod_explorer_report()
    assert report["count"] == 2
    by_mod = {r["mod"]: r for r in report["rows"]}
    assert by_mod["Swordflight"]["rating"] == "Excellent"
    assert by_mod["Swordflight"]["completed"] == 2
    assert by_mod["Abyss"]["group"] == "Adv"


def test_mod_explorer_report_maps_sentinel_groups(qtbot, tmp_path):
    # A no-group mod must show "No Group", never the raw "......001" sentinel.
    from vaultkeeper.core import constants as C

    controller = _controller(tmp_path)
    controller.pd.add_mod(ModData(group=C.GROUP_NONE, mod_name="Loose Mod"))
    by_mod = {r["mod"]: r for r in controller.mod_explorer_report()["rows"]}
    assert by_mod["Loose Mod"]["group"] == "No Group"
    assert not by_mod["Loose Mod"]["group"].startswith("......")


def test_mod_explorer_dialog(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = ModExplorer.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 2
    # Sortable table has the expected columns.
    assert dlg.table.headerItem().text(0) == "Mod"
    assert dlg.table.headerItem().text(6) == "Completed"


def test_mod_explorer_filter_bar(qtbot):
    report = {
        "count": 3,
        "rows": [
            {"mod": "Aribeth", "group": "Campaigns", "state": "Installed",
             "rating": "", "files": 10, "played": "", "completed": 2},
            {"mod": "Bastard", "group": "Community", "state": "Not Installed",
             "rating": "", "files": 5, "played": "", "completed": 0},
            {"mod": "Aftermath", "group": "Campaigns", "state": "Installed",
             "rating": "", "files": 3, "played": "", "completed": 0},
        ],
    }
    dlg = ModExplorer(report)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 3

    dlg._search.setText("af")  # name substring
    assert dlg.table.topLevelItemCount() == 1  # Aftermath

    dlg._search.clear()
    dlg._state.setCurrentText("Not Installed")
    assert dlg.table.topLevelItemCount() == 1  # Bastard

    dlg._state.setCurrentIndex(0)  # All states
    dlg._only_completed.setChecked(True)
    assert dlg.table.topLevelItemCount() == 1  # Aribeth (completed=2)


def test_mod_explorer_has_help_button(qtbot, tmp_path):
    # VB ModExplorer has a Help button (TsHelpExplorer → HelpFile.Open) — parity.
    from PySide6.QtWidgets import QPushButton

    dlg = ModExplorer.show_for(_controller(tmp_path))
    qtbot.addWidget(dlg)
    help_btn = next(
        b for b in dlg.findChildren(QPushButton) if b.text() == "Help"
    )
    help_btn.click()
    assert "tshelpexplorer.htm" in dlg._help_viewer.browser.source().toString().lower()


def test_mod_explorer_copy_names(qtbot):
    # Test Copy Names button copies selected mod names to clipboard.
    from PySide6.QtWidgets import QApplication, QPushButton

    report = {
        "count": 3,
        "rows": [
            {"mod": "Zulu", "group": "Campaigns", "state": "Installed",
             "rating": "", "files": 10, "played": "", "completed": 2},
            {"mod": "Yankee", "group": "Community", "state": "Not Installed",
             "rating": "", "files": 5, "played": "", "completed": 0},
            {"mod": "Xray", "group": "Campaigns", "state": "Installed",
             "rating": "", "files": 3, "played": "", "completed": 0},
        ],
    }
    dlg = ModExplorer(report)
    qtbot.addWidget(dlg)

    # Select first two mods (in sorted order: Xray, Yankee, Zulu)
    dlg.table.topLevelItem(0).setSelected(True)
    dlg.table.topLevelItem(1).setSelected(True)

    # Click Copy Names button
    copy_btn = next(
        b for b in dlg.findChildren(QPushButton) if b.text() == "Copy Names"
    )
    copy_btn.click()

    # Verify clipboard contains the mod names
    clipboard_text = QApplication.clipboard().text()
    assert "Xray" in clipboard_text
    assert "Yankee" in clipboard_text


def test_mod_explorer_select_callback(qtbot):
    # Test Select button invokes on_select callback and closes.
    from PySide6.QtWidgets import QPushButton

    report = {
        "count": 2,
        "rows": [
            {"mod": "Zebra", "group": "Adv", "state": "Installed",
             "rating": "", "files": 20, "played": "", "completed": 1},
            {"mod": "Alpha", "group": "Adv", "state": "Not Installed",
             "rating": "", "files": 15, "played": "", "completed": 0},
        ],
    }
    selected_mods = []

    def on_select(mod_name):
        selected_mods.append(mod_name)

    dlg = ModExplorer(report, on_select=on_select)
    qtbot.addWidget(dlg)

    # Select first mod in sorted order (Alpha comes before Zebra)
    dlg.table.topLevelItem(0).setSelected(True)
    dlg.table.setCurrentItem(dlg.table.topLevelItem(0))

    # Click Select button
    select_btn = next(
        b for b in dlg.findChildren(QPushButton) if b.text() == "Select"
    )
    select_btn.click()

    # Verify callback was invoked with the first sorted mod
    assert selected_mods == ["Alpha"]
    # Dialog should be closed
    assert not dlg.isVisible()


def test_mod_explorer_group_and_rating_filter(qtbot):
    # VB CommonFiltersDialogue: include/exclude by group + rating in the explorer.
    report = {
        "count": 3,
        "rows": [
            {"mod": "A", "group": "RPG", "state": "Installed", "rating": "Excellent",
             "files": 5, "played": "", "completed": 0},
            {"mod": "B", "group": "Puzzle", "state": "Installed", "rating": "Poor",
             "files": 3, "played": "", "completed": 0},
            {"mod": "C", "group": "RPG", "state": "Installed", "rating": "Poor",
             "files": 2, "played": "", "completed": 0},
        ],
    }
    dlg = ModExplorer(report)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 3

    # Exclude the Puzzle group.
    dlg._group_filters["Puzzle"] = False
    dlg._populate()
    names = {dlg.table.topLevelItem(i).text(0) for i in range(dlg.table.topLevelItemCount())}
    assert names == {"A", "C"}

    # Also exclude Poor rating -> only the Excellent RPG mod remains.
    dlg._group_filters["Puzzle"] = True
    dlg._rating_filters["Poor"] = False
    dlg._populate()
    names = {dlg.table.topLevelItem(i).text(0) for i in range(dlg.table.topLevelItemCount())}
    assert names == {"A"}


# --------------------------------------------------------------------------- #
# The filter subsystem the audit flagged (VB CmEqual/CmGreater/CmLess + friends)
# --------------------------------------------------------------------------- #
def _rating_rows():
    return {
        "rows": [
            {"mod": "Best", "group": "G", "state": "Installed", "rating": "Excellent",
             "files": 1, "played": "", "completed": 0},
            {"mod": "Mid", "group": "G", "state": "Installed", "rating": "Medium",
             "files": 1, "played": "", "completed": 0},
            {"mod": "Worst", "group": "G", "state": "Installed", "rating": "Abandoned",
             "files": 1, "played": "", "completed": 0},
        ],
        "count": 3,
    }


def _shown(dlg):
    return {dlg.table.topLevelItem(i).text(0) for i in range(dlg.table.topLevelItemCount())}


def test_rating_comparison_operators(qtbot):
    """=, worse-than and better-than, against the Ratings ordinal.

    The enum runs best to worst (Excellent 1 … Abandoned 7), so "worse than"
    means a *greater* ordinal. Getting that backwards would silently invert the
    filter, which is why each direction is asserted by name.
    """
    dlg = ModExplorer(_rating_rows())
    qtbot.addWidget(dlg)
    assert _shown(dlg) == {"Best", "Mid", "Worst"}

    dlg._rating_value.setCurrentIndex(dlg._rating_value.findData("Medium"))
    dlg._rating_op.setCurrentIndex(dlg._rating_op.findData("="))
    assert _shown(dlg) == {"Mid"}

    dlg._rating_op.setCurrentIndex(dlg._rating_op.findData(">"))
    assert _shown(dlg) == {"Worst"}, "'worse than Medium' is the higher ordinal"

    dlg._rating_op.setCurrentIndex(dlg._rating_op.findData("<"))
    assert _shown(dlg) == {"Best"}

    dlg._rating_op.setCurrentIndex(dlg._rating_op.findData(""))
    assert _shown(dlg) == {"Best", "Mid", "Worst"}, "'any' turns the comparison off"


def test_clear_text_filters_leaves_the_include_sets_alone(qtbot):
    # VB has separate Clear Text Filters and group/rating filter sets; clearing
    # the text must not quietly re-include a group the user excluded.
    dlg = ModExplorer(_rating_rows())
    qtbot.addWidget(dlg)
    dlg._search.setText("Mid")
    dlg._rating_op.setCurrentIndex(dlg._rating_op.findData("="))
    dlg._group_filters["G"] = False
    dlg._populate()
    assert _shown(dlg) == set()

    dlg._on_clear_filters()
    assert dlg._search.text() == ""
    assert dlg._rating_op.currentData() == ""
    assert dlg._group_filters["G"] is False, "the group exclusion must survive"


def test_add_to_recent_mods_calls_back(qtbot):
    added = []
    dlg = ModExplorer(_rating_rows(), on_add_recent=added.append)
    qtbot.addWidget(dlg)
    dlg.table.setCurrentItem(dlg.table.topLevelItem(0))
    dlg._on_add_to_recent()
    assert added == [dlg.table.topLevelItem(0).text(0)]


def test_reveal_folder_opens_the_mods_own_directory(qtbot, tmp_path, monkeypatch):
    from PySide6.QtGui import QDesktopServices

    (tmp_path / "Best").mkdir()
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url))

    dlg = ModExplorer(_rating_rows(), mods_dir=tmp_path)
    qtbot.addWidget(dlg)
    dlg.table.setCurrentItem(dlg.table.topLevelItem(0))
    assert dlg.table.currentItem().text(0) == "Best"
    dlg._on_reveal_folder()
    assert opened and opened[0].toLocalFile().endswith("Best")

    # A mod with no folder on disk opens nothing rather than a missing path.
    opened.clear()
    dlg.table.setCurrentItem(dlg.table.topLevelItem(2))  # "Worst" — no directory
    dlg._on_reveal_folder()
    assert opened == []


# --------------------------------------------------------------------------- #
# Mod-state comparison (VB TsStateLess / TsStateEqual / TsStateGreater)
# --------------------------------------------------------------------------- #
def _state_rows():
    from vaultkeeper.core.state import State

    def row(mod, state):
        return {
            "mod": mod, "group": "G", "state": state.name.replace("_", " ").title(),
            "state_value": int(state), "rating": "Good", "files": 1,
            "played": "", "completed": 0,
        }

    return {
        "rows": [
            row("Untouched", State.NOT_INSTALLED),
            row("Partly", State.SOME_INSTALLED),
            row("Done", State.INSTALLED),
            row("Clobbered", State.OVERRIDDEN),
        ],
        "count": 4,
    }


def test_state_comparison_finds_partly_installed_mods(qtbot):
    """VB FilterState, stated positively.

    "less files installed than Installed" is the only way the original answers
    "what is half-installed?" — the plain equality combo cannot express it.
    """
    dlg = ModExplorer(_state_rows())
    qtbot.addWidget(dlg)
    assert _shown(dlg) == {"Untouched", "Partly", "Done", "Clobbered"}

    dlg._state.setCurrentIndex(dlg._state.findData("Installed"))
    dlg._state_op.setCurrentIndex(dlg._state_op.findData("="))
    assert _shown(dlg) == {"Done"}

    dlg._state_op.setCurrentIndex(dlg._state_op.findData("<"))
    assert _shown(dlg) == {"Untouched", "Partly"}, "less installed than Installed"

    dlg._state_op.setCurrentIndex(dlg._state_op.findData(">"))
    assert _shown(dlg) == {"Clobbered"}, "more installed than Installed"


def test_all_states_ignores_the_comparison(qtbot):
    dlg = ModExplorer(_state_rows())
    qtbot.addWidget(dlg)
    dlg._state_op.setCurrentIndex(dlg._state_op.findData("<"))
    dlg._state.setCurrentIndex(0)  # "All states"
    assert len(_shown(dlg)) == 4


def test_state_falls_back_to_an_exact_match_without_an_ordinal(qtbot):
    # A report from an older controller carries no state_value; the filter must
    # still work rather than silently showing everything.
    report = _state_rows()
    for row in report["rows"]:
        del row["state_value"]
    dlg = ModExplorer(report)
    qtbot.addWidget(dlg)
    dlg._state.setCurrentIndex(dlg._state.findData("Installed"))
    dlg._state_op.setCurrentIndex(dlg._state_op.findData(">"))
    assert _shown(dlg) == {"Done"}


def test_clear_text_filters_resets_the_state_comparison(qtbot):
    dlg = ModExplorer(_state_rows())
    qtbot.addWidget(dlg)
    dlg._state.setCurrentIndex(dlg._state.findData("Installed"))
    dlg._state_op.setCurrentIndex(dlg._state_op.findData("<"))
    assert len(_shown(dlg)) == 2
    dlg._on_clear_filters()
    assert len(_shown(dlg)) == 4


# --------------------------------------------------------------------------- #
# Weapon / Start / End / Hench (VB ChWeapon, TxStart, TxEnd, TxHench)
# --------------------------------------------------------------------------- #
def _detail_rows():
    def row(mod, weapon, start, end, hench):
        return {
            "mod": mod, "group": "G", "state": "Installed", "state_value": 11,
            "rating": "Good", "files": 1, "played": "", "completed": 0,
            "weapon": weapon,
            "start": "-" if start < 0 else str(start), "start_value": start,
            "end": "-" if end < 0 else str(end), "end_value": end,
            "hench": "-" if hench < 0 else str(hench), "hench_value": hench,
        }

    return {
        "rows": [
            row("Low", "Long Sword", 1, 8, 0),
            row("Mid", "Katana", 10, 20, 2),
            row("High", "Long Sword", 20, 40, 4),
            row("Unset", "None", -1, -1, -1),
        ],
        "count": 4,
    }


def test_the_detail_columns_are_shown(qtbot):
    dlg = ModExplorer(_detail_rows())
    qtbot.addWidget(dlg)
    headers = [dlg.table.headerItem().text(i) for i in range(dlg.table.columnCount())]
    assert headers[-4:] == ["Weapon", "Start", "End", "Hench"]
    row0 = dlg.table.topLevelItem(0)
    assert row0.text(headers.index("Weapon")) == "Long Sword"
    # An unrecorded value shows as a hyphen, as VB's ToHyphenIfNegative does.
    unset = next(
        dlg.table.topLevelItem(i)
        for i in range(dlg.table.topLevelItemCount())
        if dlg.table.topLevelItem(i).text(0) == "Unset"
    )
    assert unset.text(headers.index("Start")) == "-"


def test_numeric_filters_accept_a_bare_number_and_an_operand(qtbot):
    """VB FilterNumber: a bare number means "greater than"."""
    dlg = ModExplorer(_detail_rows())
    qtbot.addWidget(dlg)

    dlg._end_filter.setText("20")            # bare == ">20"
    assert _shown(dlg) == {"High"}

    dlg._end_filter.setText("=20")
    assert _shown(dlg) == {"Mid"}

    dlg._end_filter.setText("<20")
    assert _shown(dlg) == {"Low", "Unset"}   # -1 counts as less than 20

    dlg._end_filter.setText("")
    assert len(_shown(dlg)) == 4


def test_a_half_typed_filter_does_not_empty_the_list(qtbot):
    # Typing ">" then a digit must not blank the table in between.
    dlg = ModExplorer(_detail_rows())
    qtbot.addWidget(dlg)
    dlg._start_filter.setText(">")
    assert _shown(dlg) == {"Low", "Mid", "High"}, "bare operand means > -1"
    dlg._start_filter.setText("not a number")
    assert len(_shown(dlg)) == 4, "unparseable text filters nothing"


def test_the_weapon_filter_matches_on_text(qtbot):
    dlg = ModExplorer(_detail_rows())
    qtbot.addWidget(dlg)
    dlg._weapon_filter.setText("long")
    assert _shown(dlg) == {"Low", "High"}
    dlg._weapon_filter.setText("KATANA")     # case-insensitive
    assert _shown(dlg) == {"Mid"}


def test_clear_text_filters_clears_the_new_boxes_too(qtbot):
    dlg = ModExplorer(_detail_rows())
    qtbot.addWidget(dlg)
    dlg._end_filter.setText("=20")
    dlg._weapon_filter.setText("katana")
    assert len(_shown(dlg)) == 1
    dlg._on_clear_filters()
    assert dlg._end_filter.text() == ""
    assert dlg._weapon_filter.text() == ""
    assert len(_shown(dlg)) == 4


# --------------------------------------------------------------------------- #
# Persisted group filter + Undo Group Changes (VB GroupNameFilters / TsUndoGroups)
# --------------------------------------------------------------------------- #
def _real_controller(tmp_path):
    from vaultkeeper.ui.controller import ProfileController

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    for name, group in (("Alpha", "Community"), ("Beta", "Official")):
        controller.create_mod(name, group)
    return controller


def test_group_filter_survives_reopening(qtbot, tmp_path):
    """VB writes the hidden groups on closing and re-reads them on open."""
    controller = _real_controller(tmp_path)

    dlg = ModExplorer.show_for(controller)
    qtbot.addWidget(dlg)
    assert len(_shown(dlg)) == 2
    dlg._group_filters["Community"] = False
    dlg._populate()
    assert _shown(dlg) == {"Beta"}
    dlg.done(0)  # closing is what persists it

    assert controller.group_filter_excludes() == ["Community"]

    reopened = ModExplorer.show_for(controller)
    qtbot.addWidget(reopened)
    assert _shown(reopened) == {"Beta"}, "the filter did not survive"


def test_undo_group_changes_reverts_to_the_saved_set(qtbot, tmp_path):
    controller = _real_controller(tmp_path)
    controller.save_group_filter_excludes(["Community"])

    dlg = ModExplorer.show_for(controller)
    qtbot.addWidget(dlg)
    assert _shown(dlg) == {"Beta"}

    # Change it without saving, then undo.
    dlg._group_filters["Community"] = True
    dlg._group_filters["Official"] = False
    dlg._populate()
    assert _shown(dlg) == {"Alpha"}

    dlg._on_undo_group_filters()
    assert _shown(dlg) == {"Beta"}, "undo must restore the saved filter"
    assert controller.group_filter_excludes() == ["Community"], "undo does not save"


def test_a_missing_filter_file_shows_everything(qtbot, tmp_path):
    # The default for a filter nobody has touched must be "show all", not "hide
    # all" — an empty file and a missing file are different things.
    controller = _real_controller(tmp_path)
    assert controller.group_filter_excludes() == []
    dlg = ModExplorer.show_for(controller)
    qtbot.addWidget(dlg)
    assert len(_shown(dlg)) == 2
