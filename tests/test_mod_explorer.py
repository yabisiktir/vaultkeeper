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


def test_mod_explorer_dialog(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = ModExplorer.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.table.topLevelItemCount() == 2
    # Sortable table has the expected columns.
    assert dlg.table.headerItem().text(0) == "Mod"
    assert dlg.table.headerItem().text(6) == "Completed"
