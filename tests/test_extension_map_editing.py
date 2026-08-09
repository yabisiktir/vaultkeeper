"""Define an extension map — secondary folder + exceptions (defineextension.htm).

The mapper carried both from the start (folder_moves, exception_prefixes) and
the editor exposed neither; the dialog's own docstring called secondary-folder
editing deferred. A prefix rule is how "fnt_" textures reach `override` while
every other .tga goes to its own folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.config.settings import load_settings, save_settings
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.ui.controller import ProfileController


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    settings = load_settings()
    settings.map_overrides = {}
    settings.map_exception_prefixes = {}
    save_settings(settings)
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


# -- The mapper ------------------------------------------------------------------ #
def test_a_prefix_sends_a_file_to_the_secondary_folder():
    # .hak, whose primary (hak) and secondary (patch) genuinely differ — .mdl
    # maps to override either way, so it proves nothing.
    mapper = Mapper(is_ee=True)
    assert mapper.get_secondary_folder(".hak") == "patch"
    mapper.set_exception_prefixes(".hak", ["ttr_"])

    assert mapper.get_mapped_folder("ttr_x.hak") == "patch"
    assert mapper.get_mapped_folder("other.hak") == "hak"


def test_clearing_the_prefixes_removes_the_rule():
    mapper = Mapper(is_ee=True)
    mapper.set_exception_prefixes(".tga", ["zzz_"])
    mapper.set_exception_prefixes(".tga", [])
    assert ".tga" not in mapper.exception_prefixes


def test_prefixes_are_normalised():
    """They are compared against a lower-cased name, so storing them any other
    way makes a rule that silently never matches."""
    mapper = Mapper(is_ee=True)
    mapper.set_exception_prefixes(".tga", ["  FNT_ ", "gui_", "", "FNT_"])
    assert mapper.exception_prefixes[".tga"] == ["fnt_", "gui_"]


def test_the_secondary_folder_is_overridable():
    mapper = Mapper(is_ee=True)
    mapper.set_override("folder_moves", ".mdl", "override")
    assert mapper.get_secondary_folder(".mdl") == "override"
    assert mapper.is_override("folder_moves", ".mdl")


# -- Through the controller ------------------------------------------------------- #
def test_setting_a_secondary_folder_persists(controller):
    result = controller.set_extension_secondary(".mdl", "override", ["ttr_"])

    assert result["ok"], result["message"]
    assert controller.ctx.mapper.get_secondary_folder(".mdl") == "override"
    saved = load_settings(controller._settings_path)
    assert saved.map_exception_prefixes[".mdl"] == ["ttr_"]
    assert saved.map_overrides["folder_moves"][".mdl"] == "override"


def test_an_extension_without_its_dot_still_works(controller):
    assert controller.set_extension_secondary("mdl", "override", [])["ok"]
    assert controller.ctx.mapper.get_secondary_folder(".mdl") == "override"


def test_exceptions_without_a_secondary_folder_are_refused(controller):
    """A rule that sends files somewhere, with nowhere to send them, is not a
    rule — and silently dropping half of it would be worse."""
    result = controller.set_extension_secondary(".mdl", "", ["ttr_"])
    assert not result["ok"] and "secondary folder" in result["message"]


def test_clearing_the_secondary_folder_works(controller):
    controller.set_extension_secondary(".mdl", "override", ["ttr_"])
    result = controller.set_extension_secondary(".mdl", "", [])

    assert result["ok"]
    assert controller.ctx.mapper.get_secondary_folder(".mdl") == ""


def test_saved_prefixes_are_in_force_when_the_profile_opens(controller, tmp_path):
    """Otherwise they are a setting nothing reads until Settings is opened."""
    controller.set_extension_secondary(".hak", "patch", ["ttr_"])
    saved = load_settings(controller._settings_path)

    reopened = ProfileController.open_profile(
        profile_mods_dir=controller.ctx.profile_mods_dir,
        game_root=controller.ctx.game_root,
        store_path=tmp_path / "Data" / "P2.json",
        map_overrides=saved.map_overrides,
        map_exception_prefixes=saved.map_exception_prefixes,
    )
    assert reopened.ctx.mapper.get_mapped_folder("ttr_x.hak") == "patch"


# -- The dialog -------------------------------------------------------------------- #
def test_the_row_is_only_shown_for_extensions(qtbot, controller):
    from vaultkeeper.ui.dialogs.folder_mapping import FolderMapping

    dlg = FolderMapping.show_for(controller, start_tab="Extensions")
    qtbot.addWidget(dlg)
    assert dlg._secondary_row.isVisibleTo(dlg)

    dlg.tabs.setCurrentIndex(1)  # Map Files
    assert not dlg._secondary_row.isVisibleTo(dlg)


def test_selecting_an_extension_shows_what_it_has(qtbot, controller):
    from vaultkeeper.ui.dialogs.folder_mapping import FolderMapping

    dlg = FolderMapping.show_for(controller, start_tab="Extensions")
    qtbot.addWidget(dlg)

    for i in range(dlg.extensions.topLevelItemCount()):
        if dlg.extensions.topLevelItem(i).text(0) == ".tga":
            dlg.extensions.setCurrentItem(dlg.extensions.topLevelItem(i))
            break
    assert dlg._secondary_combo.currentText() == "override"
    assert "fnt_" in dlg._prefixes_edit.text()
