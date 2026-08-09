"""Player or Mod Builder (VB CheckPlayerExcludes / PlayerExcludes).

The fourth of the five first-run questions the port had never asked. It decides
what Create Installer leaves out — builder resources, script templates, and the
starter modules that ship inside community packs — and it is the last thing
anybody wants to discover after building thirty installers.

Found from communitypatchprojectcpp.htm, which tells people that "the 1.72
builder resources entry in the Map Exclusions page controls whether CPP's
Builder Resources are included" — an entry this port did not have.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.config.settings import load_settings, save_settings
from vaultkeeper.core.mapper import (
    PLAYER_EXCLUDE_FILES,
    PLAYER_EXCLUDE_FOLDERS,
    PLAYER_EXCLUDE_MODS,
    Mapper,
)
from vaultkeeper.ui.controller import ProfileController


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    settings = load_settings()
    settings.asked_player_excludes = False
    settings.map_exclude_overrides = {}
    save_settings(settings)
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


# -- The lists ------------------------------------------------------------------- #
def test_the_entry_the_help_names_exists():
    """communitypatchprojectcpp.htm: "Remove 1.72 builder resources to include
    CPP's Builder Resources in the Mod Installer." Advice you cannot follow."""
    assert "1.72 builder resources" in PLAYER_EXCLUDE_FOLDERS

    mapper = Mapper(is_ee=True)
    assert not mapper.is_excluded_folder("1.72 builder resources")
    mapper.apply_player_excludes()
    assert mapper.is_excluded_folder("1.72 builder resources")


def test_the_starter_modules_inside_community_packs_are_excluded():
    mapper = Mapper(is_ee=True)
    mapper.apply_player_excludes()
    assert mapper.is_demo_mod("CEPv22_starter.mod")
    assert mapper.is_demo_mod("Q_Base_something.mod")
    assert not mapper.is_demo_mod("Swordflight Chapter 1.mod")


def test_applying_twice_adds_nothing_the_second_time():
    """It is additive, and runs once — but a list the user has since edited must
    not be reset by a second call either."""
    mapper = Mapper(is_ee=True)
    first = mapper.apply_player_excludes()
    assert first == len(PLAYER_EXCLUDE_MODS) + len(PLAYER_EXCLUDE_FILES) + len(
        PLAYER_EXCLUDE_FOLDERS
    )
    assert mapper.apply_player_excludes() == 0


def test_missing_count_reports_what_is_not_there():
    mapper = Mapper(is_ee=True)
    assert mapper.missing_player_excludes() > 0
    mapper.apply_player_excludes()
    assert mapper.missing_player_excludes() == 0


# -- Asking, once ----------------------------------------------------------------- #
def test_the_question_is_pending_until_it_is_answered(controller):
    assert controller.player_excludes_pending() > 0
    controller.answer_player_excludes(player=True)
    assert controller.player_excludes_pending() == 0


def test_answering_player_adds_them_and_persists(controller):
    result = controller.answer_player_excludes(player=True)

    assert result["added"] > 0
    assert controller.ctx.mapper.is_excluded_folder("scripttemplates")
    saved = load_settings(controller._settings_path)
    assert saved.asked_player_excludes is True
    assert saved.map_exclude_overrides, "the additions are written to settings"


def test_answering_builder_adds_nothing(controller):
    """That is the whole of the difference: the excluded items are the ones only
    a module builder wants."""
    result = controller.answer_player_excludes(player=False)

    assert result["added"] == 0
    assert not controller.ctx.mapper.is_excluded_folder("scripttemplates")
    assert load_settings(controller._settings_path).asked_player_excludes is True


def test_it_is_not_asked_again(controller):
    controller.answer_player_excludes(player=False)
    assert controller.player_excludes_pending() == 0


def test_the_window_asks_only_when_it_is_pending(qtbot, controller, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller)
    qtbot.addWidget(win)

    shown: list[int] = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(1))
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)

    win.offer_player_excludes()
    assert shown == [1]

    win.offer_player_excludes()
    assert shown == [1], "answered once, never asked again"


def test_the_additions_survive_a_restart(controller, tmp_path):
    """An exclusion that cannot be persisted is one that comes back every launch
    — which is why "mods" had to become an overridable kind."""
    controller.answer_player_excludes(player=True)
    saved = load_settings(controller._settings_path)

    reopened = ProfileController.open_profile(
        profile_mods_dir=controller.ctx.profile_mods_dir,
        game_root=controller.ctx.game_root,
        store_path=tmp_path / "Data" / "Again.json",
        map_exclude_overrides=saved.map_exclude_overrides,
    )
    assert reopened.ctx.mapper.is_demo_mod("CEPv22_starter.mod")
    assert reopened.ctx.mapper.is_excluded_folder("scripttemplates")
