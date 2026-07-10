"""Dialog test for the Start Screen Manager gallery (VB StartScreenManager)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from pathlib import Path  # noqa: E402

from vaultkeeper.game import start_screen as ss  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.start_screen_manager import StartScreenManager  # noqa: E402


def _controller_with_images(tmp_path: Path, names: list[str]) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.create_mod(ss.LOADSCREEN_MOD)
    folder = controller.ctx.profile_mods_dir / ss.LOADSCREEN_MOD / ss.SCREEN_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"x" * 16)
    return controller


def _report() -> dict:
    return {
        "exists": True,
        "mod_name": "NWN Loadscreens (NIT Managed)",
        "installed": True,
        "active": "sunset.tga",
        "image_folder": "/mods/NWN Loadscreens (NIT Managed)/Loadscreen Images",
        "images": [
            {
                "name": "castle.tga",
                "path": "/x/castle.tga",
                "size": 100,
                "size_text": "100 B",
                "excluded": True,
                "active": False,
            },
            {
                "name": "sunset.tga",
                "path": "/x/sunset.tga",
                "size": 200,
                "size_text": "200 B",
                "excluded": False,
                "active": True,
            },
        ],
        "count": 2,
        "excluded_count": 1,
        "summary": "2 loadscreen images · 'sunset.tga' installed · 1 auto-excluded.",
    }


def test_dialog_population(qtbot) -> None:
    dlg = StartScreenManager(_report())
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 2
    # Active image gets the ★ marker.
    labels = [dlg._list.item(i).text() for i in range(dlg._list.count())]
    assert any("★" in label and "sunset.tga" in label for label in labels)
    assert "auto-excluded" in dlg._summary.text().lower()


def test_dialog_empty_report(qtbot) -> None:
    report = {
        "exists": False,
        "mod_name": "NWN Loadscreens (NIT Managed)",
        "installed": False,
        "active": "",
        "image_folder": "",
        "images": [],
        "count": 0,
        "excluded_count": 0,
        "summary": "NIT does not yet manage your NWN Start Screen.",
    }
    dlg = StartScreenManager(report)
    qtbot.addWidget(dlg)
    assert dlg._list.count() == 0
    assert "no loadscreen images" in dlg._preview.text().lower()


def test_toggle_exclude_action(qtbot, tmp_path: Path) -> None:
    controller = _controller_with_images(tmp_path, ["a.tga", "b.tga"])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)

    # Select "a.tga" and exclude it.
    dlg._list.setCurrentRow(0)
    assert dlg._current_entry()["name"] == "a.tga"
    dlg._on_toggle_exclude()

    assert ss.read_auto_excludes(controller._profile_data_dir()) == ["a.tga"]
    # The list reselects a.tga and now shows it as excluded.
    assert dlg._current_entry()["name"] == "a.tga"
    assert dlg._current_entry()["excluded"] is True
    assert dlg._clear_btn.isEnabled() is True

    # Toggle again → un-excluded.
    dlg._on_toggle_exclude()
    assert ss.read_auto_excludes(controller._profile_data_dir()) == []
    assert dlg._current_entry()["excluded"] is False


def test_clear_exclusions_action(qtbot, tmp_path: Path) -> None:
    controller = _controller_with_images(tmp_path, ["a.tga", "b.tga"])
    controller.add_loadscreen_exclusion("a.tga")
    controller.add_loadscreen_exclusion("b.tga")
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg._clear_btn.isEnabled() is True

    dlg._on_clear_exclusions()
    assert ss.read_auto_excludes(controller._profile_data_dir()) == []
    assert dlg._clear_btn.isEnabled() is False


# -- Action buttons drive the controller (VB RbInstall/RbDeleteFile/etc.) --- #


def test_dialog_install_button(qtbot, tmp_path):
    controller = _controller_with_images(tmp_path, ["Winter.tga", "Summer.tga"])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    # Select the first image and install it.
    dlg._list.setCurrentRow(0)
    name = dlg._current_entry()["name"]
    dlg._on_install()
    game_screen = controller.ctx.game_folders["override"] / ss.NWN_START_SCREEN_NAME
    assert game_screen.is_file()
    info = ss.read_start_screen_info(controller._profile_data_dir())
    assert info.active_screen == name


def test_dialog_delete_button(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    controller = _controller_with_images(tmp_path, ["Winter.tga", "Summer.tga"])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    dlg._list.setCurrentRow(0)
    target = dlg._current_entry()["name"]
    dlg._on_delete()
    folder = controller._loadscreen_image_folder(controller.pd.mod_item(ss.LOADSCREEN_MOD))
    assert not (folder / target).is_file()


def test_dialog_add_folder_button(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    controller = _controller_with_images(tmp_path, [])
    src = tmp_path / "browse"
    src.mkdir()
    (src / "new.tga").write_bytes(b"x")
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(src))
    )
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    dlg._on_add_folder()
    folder = controller._loadscreen_image_folder(controller.pd.mod_item(ss.LOADSCREEN_MOD))
    assert (folder / "new.tga").is_file()
