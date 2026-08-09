"""The Wizard Builder's archive views (newtopic21.htm).

"Alternative Ki Strikes provides a single Rar file containing folders for each
available Ki Strike colour. Only one colour can be installed at a time. […]
Select Archive Sub-Folders from the View box."

The port listed only the mod's loose files, so a mod whose alternatives live
*inside* an archive had nothing to build a wizard from — none of its options are
loose files. The dialog's own docstring called this deferred.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from vaultkeeper.ui.controller import ProfileController


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    # Wizard sources are what goes *into* an installer, not what is already in
    # one: loose files in the mod folder and the archives in _Downloads.
    # .Mod Installer is the output and is not scanned — two earlier versions of
    # this fixture put files there and made the code look broken.
    mod = tmp_path / "Profiles" / "P" / "Ki Strikes"
    mod.mkdir(parents=True)
    (mod / "kistrikes.hak").write_bytes(b"loose")
    downloads = mod / "_Downloads"
    downloads.mkdir(parents=True)
    archive = downloads / "kistrikes.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Blue/ki_blue.tga", "x")
        zf.writestr("Red/ki_red.tga", "x")
        zf.writestr("Green/ki_green.tga", "x")
        zf.writestr("loose_in_archive.tga", "x")
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_the_files_view_lists_the_mods_own_files(controller):
    keys = controller.wizard_source_files("Ki Strikes")
    assert any(k.endswith("kistrikes.hak") for k in keys)
    assert not any("Blue" in k for k in keys), "the archive has not been opened"


def test_the_folders_view_lists_one_entry_per_archive_folder(controller):
    """That is what a "pick one of these" wizard is built from."""
    keys = controller.wizard_source_files("Ki Strikes", view="folders")
    names = {k.rsplit("\\", 1)[-1] for k in keys}
    assert names == {"Blue", "Red", "Green"}


def test_a_file_at_an_archives_root_is_not_a_folder_choice(controller):
    keys = controller.wizard_source_files("Ki Strikes", view="folders")
    assert not any("loose_in_archive" in k for k in keys)


def test_the_folder_files_view_lists_everything_inside(controller):
    keys = controller.wizard_source_files("Ki Strikes", view="folder_files")
    assert any(k.endswith("ki_blue.tga") for k in keys)
    assert any(k.endswith("loose_in_archive.tga") for k in keys)


def test_a_mod_with_no_archives_gives_no_folder_entries(tmp_path):
    plain = tmp_path / "Profiles" / "P" / "Plain"
    plain.mkdir(parents=True)
    (plain / "a.hak").write_bytes(b"x")
    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    assert c.wizard_source_files("Plain", view="folders") == []


def test_the_dialog_offers_the_three_views(qtbot, controller):
    from vaultkeeper.ui.dialogs.wizard_builder import WizardBuilder

    dlg = WizardBuilder.show_for(controller, "Ki Strikes")
    qtbot.addWidget(dlg)

    labels = [dlg.view_combo.itemText(i) for i in range(dlg.view_combo.count())]
    assert labels == ["Files", "Archive Sub-Folders", "Archive Folder Files"]


def test_switching_the_view_refills_the_source_list(qtbot, controller):
    from vaultkeeper.ui.dialogs.wizard_builder import WizardBuilder

    dlg = WizardBuilder.show_for(controller, "Ki Strikes")
    qtbot.addWidget(dlg)
    dlg.view_combo.setCurrentIndex(1)  # Archive Sub-Folders

    listed = [dlg.source_list.item(i).text() for i in range(dlg.source_list.count())]
    assert any("Blue" in text for text in listed), listed
