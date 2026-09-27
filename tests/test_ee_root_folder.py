"""On EE the game's root folder ("nwn") is the user files folder (audit M3).

NIT's live folder table maps "nwn" to the user folder for an EE profile, so a
mod's .ini/.tml/.key/.dll/dialog.tlk install there, and nwn.ini / settings.tml
are recorded as installed files. Vaultkeeper used the install folder: root files
landed in the game's installation, and the user folder's own INI files were
invisible (so the INI auto-restorer found nothing). Profiles made by older
versions are migrated when opened.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.ui.controller import ProfileController


def _open(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "install",
        store_path=tmp_path / "Data" / "P.json",
        is_ee=True,
        game_user_dir=tmp_path / "user",
    )


def _setup(tmp_path: Path) -> None:
    (tmp_path / "install").mkdir()
    (tmp_path / "install" / "steam_appid.txt").write_text("704450")
    (tmp_path / "user").mkdir()
    (tmp_path / "user" / "nwn.ini").write_text("[Alias]\n")


def _alpha_with_root_file(c: ProfileController, tmp_path: Path) -> None:
    c.create_mod("Alpha Pack")
    source = tmp_path / "Profiles" / "P" / "Alpha Pack"
    (source / "alpha.ini").write_text("ALPHA INI")
    (source / "alpha.hak").write_text("A")
    assert c.build_installer_payload("Alpha Pack")["ok"]
    c.install(["Alpha Pack"])


def test_ee_root_files_install_into_the_user_folder(tmp_path: Path) -> None:
    _setup(tmp_path)
    c = _open(tmp_path)

    _alpha_with_root_file(c, tmp_path)

    assert (tmp_path / "user" / "alpha.ini").read_text() == "ALPHA INI"
    assert not (tmp_path / "install" / "alpha.ini").exists()
    # The user folder's own INI is a recorded game file, the install's files are not.
    assert c.pd.installed_item(FileKeyInfo.installed(C.MOD_ROOT_FOLDER, "nwn.ini")) is not None
    assert c.pd.installed_item(FileKeyInfo.installed(C.MOD_ROOT_FOLDER, "steam_appid.txt")) is None


def test_a_root_file_an_older_version_put_in_the_install_folder_is_moved(tmp_path: Path) -> None:
    _setup(tmp_path)
    c = _open(tmp_path)
    _alpha_with_root_file(c, tmp_path)
    # Recreate the old layout: the mod's root file sits in the install folder.
    (tmp_path / "user" / "alpha.ini").replace(tmp_path / "install" / "alpha.ini")

    reopened = _open(tmp_path)

    assert (tmp_path / "user" / "alpha.ini").read_text() == "ALPHA INI"
    assert not (tmp_path / "install" / "alpha.ini").exists()
    assert (tmp_path / "install" / "steam_appid.txt").exists()  # never touched
    assert reopened.pd.mod_item("Alpha Pack").installed
    assert any("Moved 1 file(s)" in n for n in reopened.startup_notes)
    # Opening again finds nothing to do.
    assert _open(tmp_path).startup_notes == []


def test_a_changed_or_clashing_file_is_left_where_it_is(tmp_path: Path) -> None:
    _setup(tmp_path)
    c = _open(tmp_path)
    _alpha_with_root_file(c, tmp_path)
    (tmp_path / "user" / "alpha.ini").replace(tmp_path / "install" / "alpha.ini")
    (tmp_path / "user" / "alpha.ini").write_text("THE USER'S OWN")

    reopened = _open(tmp_path)

    assert (tmp_path / "install" / "alpha.ini").read_text() == "ALPHA INI"
    assert (tmp_path / "user" / "alpha.ini").read_text() == "THE USER'S OWN"
    assert any("Left 1 file(s)" in n for n in reopened.startup_notes)


def test_a_file_no_longer_matching_its_mod_is_not_moved(tmp_path: Path) -> None:
    _setup(tmp_path)
    c = _open(tmp_path)
    _alpha_with_root_file(c, tmp_path)
    (tmp_path / "user" / "alpha.ini").unlink()
    (tmp_path / "install" / "alpha.ini").write_text("EDITED SINCE")

    _open(tmp_path)

    assert (tmp_path / "install" / "alpha.ini").read_text() == "EDITED SINCE"
    assert not (tmp_path / "user" / "alpha.ini").exists()


def test_the_ini_auto_restorer_sees_nwn_ini_on_ee(tmp_path: Path) -> None:
    _setup(tmp_path)
    c = _open(tmp_path)

    result = c.run_auto_restorers()

    assert result["ini"] >= 1
    backup = tmp_path / "Profiles" / "P" / C.AUTO_INI_FILES / C.MOD_INSTALLER_DIR / "nwn"
    assert (backup / "nwn.ini").read_text() == "[Alias]\n"
