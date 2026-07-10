"""Tests for the loadscreen install engine (VB CreateLoadscreenInstaller/InstallLoadscreen)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game import start_screen as ss
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_ensure_loadscreen_mod_creates_under_auto_group(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    assert md.mod_name == ss.LOADSCREEN_MOD
    assert md.group == ss.AUTO_GROUP
    assert c._loadscreen_image_folder(md).is_dir()


def test_install_loadscreen_copies_to_game_override(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    (c._loadscreen_image_folder(md) / "Winter.tga").write_bytes(b"TGADATA")

    res = c.install_loadscreen("Winter.tga")
    assert res["ok"]
    game_screen = c.ctx.game_folders["override"] / ss.NWN_START_SCREEN_NAME
    assert game_screen.is_file()
    assert game_screen.read_bytes() == b"TGADATA"
    assert c.pd.mod_item(ss.LOADSCREEN_MOD).installed


def test_install_loadscreen_records_active_screen(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    (c._loadscreen_image_folder(md) / "Winter.tga").write_bytes(b"x")

    c.install_loadscreen("Winter.tga")
    info = ss.read_start_screen_info(c._profile_data_dir())
    assert info is not None
    assert info.active_screen == "Winter.tga"
    assert info.standard_active


def test_install_loadscreen_missing_image(tmp_path):
    c = _controller(tmp_path)
    c.ensure_loadscreen_mod()
    res = c.install_loadscreen("Nope.tga")
    assert not res["ok"]
    assert "not found" in res["message"]


def test_install_loadscreen_no_managed_mod(tmp_path):
    c = _controller(tmp_path)
    res = c.install_loadscreen("Winter.tga")
    assert not res["ok"]


def test_reinstall_switches_active_image(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    folder = c._loadscreen_image_folder(md)
    (folder / "Winter.tga").write_bytes(b"WINTER")
    (folder / "Summer.tga").write_bytes(b"SUMMER")

    c.install_loadscreen("Winter.tga")
    c.install_loadscreen("Summer.tga")
    game_screen = c.ctx.game_folders["override"] / ss.NWN_START_SCREEN_NAME
    assert game_screen.read_bytes() == b"SUMMER"
    info = ss.read_start_screen_info(c._profile_data_dir())
    assert info.active_screen == "Summer.tga"


def test_uninstall_loadscreen_removes_from_game(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    (c._loadscreen_image_folder(md) / "Winter.tga").write_bytes(b"x")
    c.install_loadscreen("Winter.tga")
    game_screen = c.ctx.game_folders["override"] / ss.NWN_START_SCREEN_NAME
    assert game_screen.is_file()

    res = c.uninstall_loadscreen()
    assert res["ok"]
    assert not game_screen.is_file()
    assert not c.pd.mod_item(ss.LOADSCREEN_MOD).installed


# -- Add / delete images (VB ProcessFiles/ProcessFolders/RbDeleteFile) ------ #


def test_add_loadscreen_images_copies_and_dedups(tmp_path):
    c = _controller(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "Winter.tga").write_bytes(b"a")
    (src / "Summer.tga").write_bytes(b"b")

    res = c.add_loadscreen_images([src / "Winter.tga", src / "Summer.tga"])
    assert res["added"] == 2
    md = c.pd.mod_item(ss.LOADSCREEN_MOD)
    folder = c._loadscreen_image_folder(md)
    assert (folder / "Winter.tga").is_file()
    # Re-adding is skipped (no overwrite).
    res2 = c.add_loadscreen_images([src / "Winter.tga"])
    assert res2["added"] == 0 and res2["skipped"] == 1


def test_add_loadscreen_renames_reserved_name(tmp_path):
    c = _controller(tmp_path)
    src = tmp_path / "My Screen" / "override"
    src.mkdir(parents=True)
    (src / "gui_pre_bknd3.tga").write_bytes(b"x")

    c.add_loadscreen_images([src / "gui_pre_bknd3.tga"])
    md = c.pd.mod_item(ss.LOADSCREEN_MOD)
    assert (c._loadscreen_image_folder(md) / "My Screen.tga").is_file()


def test_add_loadscreen_folders_recurses(tmp_path):
    c = _controller(tmp_path)
    root = tmp_path / "browse"
    (root / "sub").mkdir(parents=True)
    (root / "a.tga").write_bytes(b"x")
    (root / "sub" / "b.tga").write_bytes(b"x")

    res = c.add_loadscreen_folders([root])
    assert res["added"] == 2


def test_delete_loadscreen_image_uninstalls_active(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    folder = c._loadscreen_image_folder(md)
    (folder / "Winter.tga").write_bytes(b"W")
    (folder / "Summer.tga").write_bytes(b"S")
    c.install_loadscreen("Winter.tga")
    game_screen = c.ctx.game_folders["override"] / ss.NWN_START_SCREEN_NAME
    assert game_screen.is_file()

    res = c.delete_loadscreen_images(["Winter.tga"])
    assert res["deleted"] == 1
    assert not (folder / "Winter.tga").is_file()
    # Active image deleted → uninstalled from game + next reselected as active.
    assert not game_screen.is_file()
    info = ss.read_start_screen_info(c._profile_data_dir())
    assert info.active_screen == "Summer.tga"


def test_delete_loadscreen_prunes_exclusions(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    folder = c._loadscreen_image_folder(md)
    (folder / "Winter.tga").write_bytes(b"x")
    c.add_loadscreen_exclusion("Winter.tga")

    c.delete_loadscreen_images(["Winter.tga"])
    assert ss.read_auto_excludes(c._profile_data_dir()) == []


# -- Rename (VB RbRename @1243) — LANDMINE, bug replicated ------------------ #


def test_rename_loadscreen_basic(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    folder = c._loadscreen_image_folder(md)
    (folder / "Old.tga").write_bytes(b"x")

    res = c.rename_loadscreen_image("Old.tga", "New.tga")
    assert res["ok"]
    assert not (folder / "Old.tga").is_file()
    assert (folder / "New.tga").is_file()


def test_rename_loadscreen_rejects_invalid(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    (c._loadscreen_image_folder(md) / "Old.tga").write_bytes(b"x")
    res = c.rename_loadscreen_image("Old.tga", "gui_pre_bknd3.tga")
    assert not res["ok"] and "reserved" in res["message"]


def test_rename_installed_replicates_vb_bug(tmp_path):
    """VB @1271 writes a display name into the active-TYPE slot — corruption."""
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    folder = c._loadscreen_image_folder(md)
    (folder / "Winter.tga").write_bytes(b"x")
    c.install_loadscreen("Winter.tga")  # Winter is the active/installed image

    c.rename_loadscreen_image("Winter.tga", "Spring.tga", replicate_vb_bug=True)
    # The bug: line 0 of StartscreenInfo.txt is the renamed display name, not "1"/"2".
    raw = (c._profile_data_dir() / ss.INFO_FILENAME).read_text().splitlines()
    assert raw[0] == "Spring.tga"  # corrupted active-type slot (faithful to VB)


def test_rename_installed_corrected_behaviour(tmp_path):
    c = _controller(tmp_path)
    md = c.ensure_loadscreen_mod()
    folder = c._loadscreen_image_folder(md)
    (folder / "Winter.tga").write_bytes(b"x")
    c.install_loadscreen("Winter.tga")

    c.rename_loadscreen_image("Winter.tga", "Spring.tga", replicate_vb_bug=False)
    info = ss.read_start_screen_info(c._profile_data_dir())
    assert info.active_type in ("1", "2")  # not corrupted
    assert info.active_screen == "Spring.tga"
