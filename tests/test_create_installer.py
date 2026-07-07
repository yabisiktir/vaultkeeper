"""Tests for New Mod + Create Installer functionality."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_create_mod_makes_folder_and_row(tmp_path):
    controller = _controller(tmp_path)
    assert controller.create_mod("My Adventure")
    assert "My Adventure" in controller.pd.mod_list
    installer = tmp_path / "Profiles" / "P" / "My Adventure" / C.MOD_INSTALLER_DIR
    assert installer.is_dir()
    # The store was persisted.
    assert (tmp_path / "Data" / "P.json").exists()


def test_create_mod_rejects_duplicate(tmp_path):
    controller = _controller(tmp_path)
    assert controller.create_mod("Dup")
    assert not controller.create_mod("Dup")


def test_create_installer_writes_identifier_and_scans(tmp_path):
    controller = _controller(tmp_path)
    controller.create_mod("My Adventure")
    # Drop a payload file so the scan has something to register.
    payload = (
        tmp_path / "Profiles" / "P" / "My Adventure" / C.MOD_INSTALLER_DIR / "hak" / "a.hak"
    )
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"HAKDATA")

    assert controller.create_installer("My Adventure")
    md = controller.pd.mod_item("My Adventure")
    assert md.is_installer()
    # The identifier file exists on disk.
    ident = (
        tmp_path / "Profiles" / "P" / "My Adventure" / C.MOD_INSTALLER_DIR
        / C.MOD_NIT_DIR / f"My Adventure{C.EXT_INSTALLER}"
    )
    assert ident.is_file()
    # The payload file is now tracked.
    assert any(fk.filename == "a.hak" for fk in md.files)


def test_create_installer_unknown_mod(tmp_path):
    controller = _controller(tmp_path)
    assert not controller.create_installer("Nope")


def test_new_mod_via_window(qtbot, tmp_path):
    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert controller.create_mod("Windowed Mod")
    win.refresh()
    labels = []
    for i in range(win._tree.topLevelItemCount()):
        group = win._tree.topLevelItem(i)
        for j in range(group.childCount()):
            labels.append(group.child(j).text(0))
    assert any("Windowed Mod" in label for label in labels)
