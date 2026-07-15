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
