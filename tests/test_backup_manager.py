"""The Backup and Export Manager (VB MsBackupManager / bhbackupmanager.htm).

The menu item existed and did nothing, and CAPABILITY_STATUS recorded
databackups.htm as ported on the strength of Backup Data / Restore Data — which
do work. The *manager* screen, which is what corruptedprofiledata.htm sends you
to, did not exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.backup_manager import BackupManager


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.store_root = str(tmp_path / "Store")
    save_settings(settings)

    store = settings.resolved_store()
    store.ensure()
    (store.backups / "Main (pre-rebuild 2026-08-01 120000).json").write_text("{}")
    (store.backups / "Data 2026-08-01.zip").write_bytes(b"PK\x03\x04")
    (store.exported_settings / "settings-2026-08-01.json").write_text("{}")
    exported = store.root / "Exported Mods"
    exported.mkdir(parents=True, exist_ok=True)
    (exported / "Swordflight.vkmod").write_bytes(b"x" * 10)

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=store.data / "P.json",
    )


def test_the_report_separates_the_three_kinds(controller):
    """They are restored by three different routes, so one list would be a lie."""
    report = controller.backup_manager_report()
    assert [r["name"] for r in report["exported_settings"]] == ["settings-2026-08-01.json"]
    assert [r["name"] for r in report["exported_mods"]] == ["Swordflight.vkmod"]
    names = {r["name"] for r in report["data_backups"]}
    assert names == {"Main (pre-rebuild 2026-08-01 120000).json", "Data 2026-08-01.zip"}


def test_the_dialog_lists_everything_and_says_where(qtbot, controller):
    dlg = BackupManager.show_for(controller)
    qtbot.addWidget(dlg)

    assert dlg.tabs.count() == 3
    assert dlg.tables["data_backups"].topLevelItemCount() == 2
    assert "Exported Mods" in dlg.folders["exported_mods"].text()
    assert "4 backup" in dlg.summary.text()


def test_only_a_profile_store_backup_offers_restore(qtbot, controller):
    """An archive needs unpacking, which is what Restore Data is for — offering
    Restore for it here would promise something this screen cannot do."""
    dlg = BackupManager.show_for(controller)
    qtbot.addWidget(dlg)
    table = dlg.tables["data_backups"]

    def select(suffix: str) -> None:
        table.clearSelection()
        for i in range(table.topLevelItemCount()):
            item = table.topLevelItem(i)
            if item.text(0).endswith(suffix):
                item.setSelected(True)

    select(".json")
    assert dlg.restore_button.isEnabled()
    select(".zip")
    assert not dlg.restore_button.isEnabled()
    assert dlg.delete_button.isEnabled(), "but anything can be deleted"


def test_restoring_puts_the_profile_store_back(qtbot, controller, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    store = controller._settings().resolved_store()
    (store.data / "Main.json").write_text('{"which": "broken"}')
    (store.backups / "Main (pre-rebuild 2026-08-01 120000).json").write_text(
        '{"which": "good"}'
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)

    dlg = BackupManager.show_for(controller)
    qtbot.addWidget(dlg)
    table = dlg.tables["data_backups"]
    for i in range(table.topLevelItemCount()):
        if table.topLevelItem(i).text(0).endswith(".json"):
            table.topLevelItem(i).setSelected(True)
    dlg._on_restore()

    assert '"good"' in (store.data / "Main.json").read_text()


def test_deleting_honours_the_recycle_preference(controller):
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.recycle_on_delete = False  # permanent, so the test can see it go
    save_settings(settings)

    target = controller._settings().resolved_store().exported_settings / "settings-2026-08-01.json"
    result = controller.delete_backup_files([str(target)])

    assert result["ok"] and result["removed"] == 1
    assert "permanently" in result["message"]
    assert not target.exists()


def test_an_empty_store_says_so(qtbot, tmp_path):
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.store_root = str(tmp_path / "Empty")
    save_settings(settings)
    settings.resolved_store().ensure()

    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    dlg = BackupManager(c.backup_manager_report(), c)
    qtbot.addWidget(dlg)
    assert "Nothing has been backed up" in dlg.summary.text()
