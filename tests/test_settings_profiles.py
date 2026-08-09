"""The Profiles page (definenewprofiles.htm / specifyaneverwinternightsfolder.htm).

"Use the Profiles page in Advanced Settings to […] specify an existing
Neverwinter Nights folder for your Profile." Creating a profile against a chosen
folder already worked; repointing an existing one had nowhere to happen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.config.settings import Settings, load_settings
from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog
from vaultkeeper.ui.session import configure_profile


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.store_root = str(tmp_path / "Store")
    s.game_user_path = str(tmp_path / "user")
    sp = tmp_path / "settings.json"
    configure_profile(
        str(tmp_path / "LiveNWN"), "Live", is_ee=True, settings=s, settings_path=sp
    )
    configure_profile(
        str(tmp_path / "OldNWN"), "Classic", is_ee=False, settings=s, settings_path=sp
    )
    return load_settings(sp)


def _page(qtbot, settings: Settings) -> SettingsDialog:
    dlg = SettingsDialog(settings, None)
    qtbot.addWidget(dlg)
    return dlg


def test_it_lists_every_profile_with_its_edition_and_folder(qtbot, settings, tmp_path):
    dlg = _page(qtbot, settings)
    rows = {
        dlg.profiles_tree.topLevelItem(i).text(0): (
            dlg.profiles_tree.topLevelItem(i).text(1),
            dlg.profiles_tree.topLevelItem(i).text(2),
        )
        for i in range(dlg.profiles_tree.topLevelItemCount())
    }
    assert rows["Live"] == ("Enhanced Edition", str(tmp_path / "LiveNWN"))
    assert rows["Classic"] == ("Neverwinter Nights", str(tmp_path / "OldNWN"))


def test_the_loaded_profile_is_marked(qtbot, settings):
    dlg = _page(qtbot, settings)
    active = [
        dlg.profiles_tree.topLevelItem(i)
        for i in range(dlg.profiles_tree.topLevelItemCount())
        if dlg.profiles_tree.topLevelItem(i).text(0) == settings.active_profile
    ][0]
    assert active.font(0).bold()


def test_repointing_one_profile_leaves_the_others_alone(qtbot, settings, tmp_path):
    dlg = _page(qtbot, settings)
    dlg._profile_folder_edits["Classic"] = str(tmp_path / "MovedNWN")
    dlg.apply_to(settings)

    assert settings.profile_game_paths["Classic"] == str(tmp_path / "MovedNWN")
    assert settings.profile_game_paths["Live"] == str(tmp_path / "LiveNWN")


def test_an_untouched_profile_keeps_what_it_had(qtbot, settings, tmp_path):
    """Only the folders actually changed are written — a page that rewrites
    every row would overwrite a path set somewhere else."""
    before = dict(settings.profile_game_paths)
    dlg = _page(qtbot, settings)
    dlg.apply_to(settings)
    assert settings.profile_game_paths == before


def test_repointing_the_loaded_profile_moves_the_live_path_too(qtbot, settings, tmp_path):
    """The active profile's folder is also the one the app is using now, so the
    two must not be allowed to disagree."""
    settings.active_profile = "Live"
    dlg = _page(qtbot, settings)
    dlg._profile_folder_edits["Live"] = str(tmp_path / "MovedNWN")
    dlg.apply_to(settings)

    assert settings.nwn_path == str(tmp_path / "MovedNWN")


def test_the_edition_is_shown_but_not_editable(qtbot, settings):
    """"You cannot change the Profile Type after the Profile has been created" —
    every file key the profile holds was written against the layout it chose."""
    dlg = _page(qtbot, settings)
    item = dlg.profiles_tree.topLevelItem(0)
    from PySide6.QtCore import Qt

    assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)
    assert dlg.profile_folder_button.text().startswith("Neverwinter Nights Folder")
