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
