"""Tests for the User Response Editor (controller report/delete + dialog)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.user_response_editor import UserResponseEditor  # noqa: E402


def _controller_with_responses(tmp_path: Path) -> ProfileController:
    user = tmp_path / "gameuser"
    (user / "saves").mkdir(parents=True)
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.ctx.game_user_dir = user
    uc = controller.play_loop.game_mapper.user_choices
    uc.add_choice("Chosen Mod")
    uc.log_to_mod_names["LogA"] = "Mod A"
    uc.sav_to_mod_names["SaveB"] = "Mod B"
    uc.profile_choices["SaveC"] = "Mod C"
    return controller


def test_report_groups_all_four_categories(tmp_path):
    controller = _controller_with_responses(tmp_path)
    report = controller.user_responses_report()
    titles = [g["title"] for g in report["groups"]]
    assert titles == [
        "Mod Choices",
        "Log to Mod Names",
        "Game Save Name to Mod Names",
        "Game Save Name to Profile Mod Names",
    ]
    mod_choices = report["groups"][0]
    assert mod_choices["rows"] == [
        {"identifier": "N/A", "mod_name": "Chosen Mod", "key": "Chosen Mod"}
    ]
    log = report["groups"][1]["rows"][0]
    assert log == {"identifier": "LogA", "mod_name": "Mod A", "key": "LogA"}


def test_report_empty_without_game_user_dir(tmp_path):
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods, game_root=tmp_path / "NWN"
    )
    controller.ctx.game_user_dir = None
    assert controller.user_responses_report() == {"groups": []}


def test_delete_removes_and_persists(tmp_path):
    controller = _controller_with_responses(tmp_path)
    assert controller.delete_user_response("log", "LogA")
    uc = controller.play_loop.game_mapper.user_choices
    assert "LogA" not in uc.log_to_mod_names
    assert not controller.delete_user_response("log", "LogA")  # already gone


def test_dialog_lists_and_deletes(qtbot, tmp_path):
    controller = _controller_with_responses(tmp_path)
    dlg = UserResponseEditor(controller)
    qtbot.addWidget(dlg)

    # Four group headers, each with its entries.
    assert dlg._tree.topLevelItemCount() == 4
    log_group = dlg._tree.topLevelItem(1)
    assert log_group.text(0) == "Log to Mod Names"
    assert log_group.child(0).text(0) == "LogA"

    # Select the LogA entry and delete it; it disappears on reload.
    dlg._tree.setCurrentItem(log_group.child(0))
    assert dlg._delete.isEnabled()
    dlg._on_delete()
    log_group = dlg._tree.topLevelItem(1)
    assert log_group.child(0).text(0) == "None"  # empty placeholder
    assert "LogA" not in controller.play_loop.game_mapper.user_choices.log_to_mod_names


def test_dialog_delete_disabled_on_group_header(qtbot, tmp_path):
    controller = _controller_with_responses(tmp_path)
    dlg = UserResponseEditor(controller)
    qtbot.addWidget(dlg)
    dlg._tree.setCurrentItem(dlg._tree.topLevelItem(0))  # a group header, not a row
    assert not dlg._delete.isEnabled()
