"""Tests for the Tools-menu maintenance operations."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    installer = profile_mods / "Alpha" / C.MOD_INSTALLER_DIR / "hak"
    installer.mkdir(parents=True)
    (installer / "a.hak").write_bytes(b"AAA")
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_validate_profile_data_removes_bad_dependency(tmp_path):
    controller = _controller(tmp_path)
    controller.pd.add_mod(
        ModData(group="G", mod_name="Beta", dependencies=["Ghost", "Alpha"])
    )
    message = controller.validate_profile_data()
    assert "Dependencies removed: 1" in message  # "Ghost" does not exist; "Alpha" does
    assert controller.pd.mod_item("Beta").dependencies == ["Alpha"]


def test_calculate_crcs_fills_missing_values(tmp_path):
    # VB RepairChecksums: every record with no CRC, mod and installed side.
    # The old command took only "pending" files, empty after load: a no-op.
    from vaultkeeper.core.crc import crc32_file

    controller = _controller(tmp_path)
    assert controller.calculate_crcs() == "All files have valid checksum values."
    fk = next(k for k in controller.pd.file_list if k.filename == "a.hak")
    controller.pd.file_list[fk].file_crc = 0

    message = controller.calculate_crcs("missing")

    assert "1 file(s)" in message
    path = tmp_path / "Profiles" / "P" / "Alpha" / C.MOD_INSTALLER_DIR / "hak" / "a.hak"
    assert controller.pd.file_list[fk].file_crc == crc32_file(path)
    assert (tmp_path / "Data" / "P.json").exists()


def test_calculate_crcs_for_one_file_key(tmp_path):
    controller = _controller(tmp_path)
    assert "1 file(s)" in controller.calculate_crcs("file_key", "hak\\a.hak")
    assert "No files matched" in controller.calculate_crcs("file_key", "hak\\zzz.hak")


def test_rebuild_database_from_disk(tmp_path):
    controller = _controller(tmp_path)
    # Add a mod folder directly on disk, then rebuild to pick it up.
    (tmp_path / "Profiles" / "P" / "Gamma" / C.MOD_INSTALLER_DIR / "override").mkdir(
        parents=True
    )
    (
        tmp_path / "Profiles" / "P" / "Gamma" / C.MOD_INSTALLER_DIR / "override" / "g.2da"
    ).write_bytes(b"G")
    message = controller.rebuild_database()
    assert "Database rebuilt" in message
    assert "Gamma" in controller.pd.mod_list
    # The engine/hak-patch were rebuilt against the fresh profile.
    assert controller.engine.pd is controller.pd


def test_maintenance_via_window(qtbot, tmp_path):
    from vaultkeeper.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_command("MsValidateProfileData")
    assert "Installed File Data validated" in win.nit_status.mg_info.text()
