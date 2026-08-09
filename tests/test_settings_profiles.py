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


def test_a_game_folder_can_be_created_for_the_selected_profile(
    qtbot, settings, tmp_path, monkeypatch
):
    """createaneverwinternightsfolder.htm puts this on the Profiles page, per
    profile. Making the folder and pointing the profile at it is one action, and
    the Locations page's copy can only ever affect the loaded profile."""
    from PySide6.QtWidgets import QDialog

    from vaultkeeper.ui.dialogs import create_nwn_folder as cnf

    created = str(tmp_path / "TestNWN")

    class _FakeDialog:
        created_path = created

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            _FakeDialog.seen = kwargs

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(cnf, "CreateNwnFolderDialog", _FakeDialog)
    monkeypatch.setattr(
        "vaultkeeper.ui.dialogs.settings_dialog.QDialog", QDialog, raising=False
    )

    dlg = _page(qtbot, settings)
    for i in range(dlg.profiles_tree.topLevelItemCount()):
        if dlg.profiles_tree.topLevelItem(i).text(0) == "Classic":
            dlg.profiles_tree.setCurrentItem(dlg.profiles_tree.topLevelItem(i))
    dlg._on_create_profile_folder()

    # The new folder is shown, staged, and it knows which edition to build.
    assert dlg.profiles_tree.currentItem().text(2) == created
    assert dlg._profile_folder_edits["Classic"] == created
    assert _FakeDialog.seen["is_ee"] is False
    assert _FakeDialog.seen["profile_name"] == "Classic"


def test_both_profile_buttons_need_a_selection(qtbot, settings):
    dlg = _page(qtbot, settings)
    dlg.profiles_tree.setCurrentItem(None)
    dlg._sync_profile_buttons()
    assert not dlg.profile_folder_button.isEnabled()
    assert not dlg.profile_create_button.isEnabled()


# -- Removing a profile (removeaprofile.htm) ------------------------------------- #
def test_removing_deletes_the_mods_and_the_database(qtbot, settings, tmp_path):
    """"the Installer Tool deletes the Profile's directory in the NIT Store's
    Profiles and Data folders." There was no way to remove a profile at all."""
    from vaultkeeper.ui.session import delete_profile

    store = settings.resolved_store()
    (store.profile_dir("Classic") / "SomeMod").mkdir(parents=True, exist_ok=True)
    (store.data / "Classic.json").write_text("{}")

    settings.active_profile = "Live"
    result = delete_profile("Classic", settings, settings_path=tmp_path / "settings.json")

    assert result["ok"], result["message"]
    assert not store.profile_dir("Classic").exists()
    assert not (store.data / "Classic.json").exists()


def test_the_loaded_profile_is_refused(qtbot, settings, tmp_path):
    """Deleting it out from under the running window is not something to do
    politely — VB flags it for later; refusing outright is the same protection
    with less to go wrong."""
    from vaultkeeper.ui.session import delete_profile

    settings.active_profile = "Live"
    result = delete_profile("Live", settings, settings_path=tmp_path / "settings.json")

    assert not result["ok"] and "have open" in result["message"]
    assert settings.resolved_store().profile_dir("Live").exists()


def test_its_recorded_settings_go_with_it(qtbot, settings, tmp_path):
    """Otherwise a profile made later with the same name inherits the old one's
    edition and folder."""
    from vaultkeeper.ui.session import delete_profile

    settings.active_profile = "Live"
    delete_profile("Classic", settings, settings_path=tmp_path / "settings.json")

    assert "Classic" not in settings.profile_editions
    assert "Classic" not in settings.profile_game_paths


def test_removal_is_staged_until_ok(qtbot, settings, tmp_path, monkeypatch):
    """It deletes a whole collection of mods, so Cancel has to mean cancel."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    settings.active_profile = "Live"
    dlg = _page(qtbot, settings)
    for i in range(dlg.profiles_tree.topLevelItemCount()):
        if dlg.profiles_tree.topLevelItem(i).text(0) == "Classic":
            dlg.profiles_tree.setCurrentItem(dlg.profiles_tree.topLevelItem(i))
    dlg._on_remove_profile()

    assert "Classic" in dlg._profiles_to_remove
    assert dlg.profiles_tree.currentItem().font(0).strikeOut()
    assert settings.resolved_store().profile_dir("Classic").exists(), "not yet"

    dlg.apply_profile_removals(settings, tmp_path / "settings.json")
    assert not settings.resolved_store().profile_dir("Classic").exists()


def test_staging_can_be_undone(qtbot, settings, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    settings.active_profile = "Live"
    dlg = _page(qtbot, settings)
    for i in range(dlg.profiles_tree.topLevelItemCount()):
        if dlg.profiles_tree.topLevelItem(i).text(0) == "Classic":
            dlg.profiles_tree.setCurrentItem(dlg.profiles_tree.topLevelItem(i))

    dlg._on_remove_profile()
    assert dlg.profile_remove_button.text() == "Keep"
    dlg._on_remove_profile()          # the button now says Keep
    assert dlg._profiles_to_remove == set()
    assert not dlg.profiles_tree.currentItem().font(0).strikeOut()


def test_the_remove_button_is_off_for_the_loaded_profile(qtbot, settings):
    settings.active_profile = "Live"
    dlg = _page(qtbot, settings)
    for i in range(dlg.profiles_tree.topLevelItemCount()):
        item = dlg.profiles_tree.topLevelItem(i)
        dlg.profiles_tree.setCurrentItem(item)
        assert dlg.profile_remove_button.isEnabled() == (item.text(0) != "Live")
