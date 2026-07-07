"""Tests for the dependencies report + Dependency Manager dialog."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.dependency_manager import DependencyManager


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    # CEP is required by two adventures.
    controller.pd.add_mod(ModData(group="Content", mod_name="CEP"))
    controller.pd.add_mod(
        ModData(group="Adv", mod_name="Sands of Fate", dependencies=["CEP"])
    )
    controller.pd.add_mod(
        ModData(group="Adv", mod_name="Swordflight", dependencies=["CEP"])
    )
    return controller


def test_dependencies_report(qtbot, tmp_path):
    report = _controller(tmp_path).dependencies_report()
    by_mod = {r["mod"]: r for r in report["rows"]}
    # CEP is required by both adventures.
    assert set(by_mod["CEP"]["required_by"]) == {"Sands of Fate", "Swordflight"}
    # Each adventure depends on CEP.
    assert by_mod["Sands of Fate"]["depends_on"] == ["CEP"]


def test_dependency_manager_dialog(qtbot, tmp_path):
    controller = _controller(tmp_path)
    dlg = DependencyManager.show_for(controller)
    qtbot.addWidget(dlg)
    # Three rows: CEP (required by), and the two adventures (depend on).
    assert dlg.table.topLevelItemCount() == 3


def test_no_dependencies(qtbot, tmp_path):
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    assert controller.dependencies_report()["count"] == 0
