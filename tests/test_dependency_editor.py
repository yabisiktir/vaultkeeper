"""Tests for the dependency editor (VB DependencyManager per-mod editing)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.dependency_editor import DependencyEditor  # noqa: E402


def _controller(tmp_path: Path, *mods: str) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    for name in mods:
        (profile_mods / name / C.MOD_INSTALLER_DIR).mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    return controller


def test_editor_data_buckets_by_group(tmp_path):
    controller = _controller(tmp_path, "MyMod", "CEP", "Tileset")
    data = controller.dependency_editor_data("MyMod")
    assert data["mod"] == "MyMod"
    all_mods = [m for g in data["groups"] for m in g["mods"]]
    assert "CEP" in all_mods and "Tileset" in all_mods
    assert "MyMod" not in all_mods  # the edited mod excludes itself


def test_set_mod_dependencies_persists(tmp_path):
    controller = _controller(tmp_path, "MyMod", "CEP")
    result = controller.set_mod_dependencies("MyMod", ["CEP"])
    assert result["ok"]
    assert controller.pd.mod_item("MyMod").dependencies == ["CEP"]
    # Round-trips through the report.
    data = controller.dependency_editor_data("MyMod")
    assert data["dependencies"] == ["CEP"]


def test_editor_check_and_save(qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    controller = _controller(tmp_path, "MyMod", "CEP")
    dlg = DependencyEditor.show_for(controller, "MyMod")
    qtbot.addWidget(dlg)
    # Select the group containing CEP and tick it.
    dlg.group_list.setCurrentRow(0)
    # Find CEP in the mod list and check it.
    for i in range(dlg.mod_list.count()):
        item = dlg.mod_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) == "CEP":
            item.setCheckState(Qt.CheckState.Checked)
    assert "CEP" in dlg._deps
    assert dlg.dep_list.count() == 1

    import unittest.mock as mock

    with mock.patch.object(QMessageBox, "information"):
        dlg._on_save()
    assert controller.pd.mod_item("MyMod").dependencies == ["CEP"]
