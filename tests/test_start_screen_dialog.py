"""Dialog test for the Start Screen Manager gallery (VB StartScreenManager)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from pathlib import Path  # noqa: E402

from PySide6.QtCore import Qt  # noqa: E402

from vaultkeeper.game import start_screen as ss  # noqa: E402
from vaultkeeper.ui import resources as R  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.start_screen_manager import StartScreenManager  # noqa: E402


def _controller_with_images(
    tmp_path: Path, names: list[str], *, settings_path: Path | None = None
) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        # The app always supplies this (session.py: store.settings_file); tests
        # that check a *preference* have to as well, or it is written nowhere.
        settings_path=settings_path,
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
        "summary": "Vaultkeeper does not yet manage your NWN Start Screen.",
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
    # The one Options entry now offers the opposite action, rather than being a
    # "toggle" that never says which way it goes (VB shows exactly one of
    # RbAddAutoExclusion / RbRemoveAutoExclusion).
    assert dlg._exclusion_action.text() == "Remove from Auto Exclusions List"

    # Toggle again → un-excluded.
    dlg._on_toggle_exclude()
    assert ss.read_auto_excludes(controller._profile_data_dir()) == []
    assert dlg._current_entry()["excluded"] is False
    assert dlg._exclusion_action.text() == "Add to Auto Exclusions List"


def test_clear_exclusions_action(qtbot, tmp_path: Path) -> None:
    controller = _controller_with_images(tmp_path, ["a.tga", "b.tga"])
    controller.add_loadscreen_exclusion("a.tga")
    controller.add_loadscreen_exclusion("b.tga")
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg._report.get("excluded_count") == 2

    # Clearing lives in the Information Report now, where the list of what is
    # about to be cleared is in front of you (VB RbInfoReport).
    dlg._on_clear_exclusions()
    assert ss.read_auto_excludes(controller._profile_data_dir()) == []
    assert dlg._report.get("excluded_count") == 0


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


# --------------------------------------------------------------------------- #
# The controls the help topic documents (VB RbToolstrip + RbOptions + BtSearch)
# --------------------------------------------------------------------------- #
def test_the_ribbon_uses_the_originals_buttons_and_order(qtbot, tmp_path):
    """Same icons, same order, same separators as StartScreenManager.Designer.vb.

    Identical UX is the point of the port: a screen with the right actions but
    invented text buttons is a different program that happens to do the same
    things.
    """
    controller = _controller_with_images(tmp_path, ["a.tga"])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)

    labels = [entry[1] for entry in dlg._TOOLBAR if entry is not None]
    assert labels == [
        "Previous", "Next", "Add Folders", "Add Files",
        "Rename", "Export", "Delete", "Install",
    ]
    # Every icon named in the Designer must actually resolve to a shipped image.
    for entry in dlg._TOOLBAR:
        if entry is None:
            continue
        assert not R.get_icon(entry[2]).isNull(), f"missing icon: {entry[2]}"


def test_previous_and_next_walk_the_images(qtbot, tmp_path):
    controller = _controller_with_images(tmp_path, ["a.tga", "b.tga", "c.tga"])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)

    assert dlg._list.currentRow() == 0
    assert not dlg._prev_btn.isEnabled()
    dlg._move(1)
    assert dlg._list.currentRow() == 1
    dlg._move(1)
    assert dlg._list.currentRow() == 2
    assert not dlg._next_btn.isEnabled()
    dlg._move(1)  # off the end: stays put
    assert dlg._list.currentRow() == 2


def test_the_search_box_only_appears_past_ten_images(qtbot, tmp_path):
    # VB: "The search capability is only enabled when you have 10 or more start
    # screen images."
    few = _controller_with_images(tmp_path / "few", [f"{n}.tga" for n in range(3)])
    dlg = StartScreenManager.show_for(few)
    qtbot.addWidget(dlg)
    assert not dlg._search_action.isVisible()

    many = _controller_with_images(tmp_path / "many", [f"{n:02d}.tga" for n in range(12)])
    dlg2 = StartScreenManager.show_for(many)
    qtbot.addWidget(dlg2)
    assert not dlg2._search.isHidden()


def test_navigation_follows_the_search_filter(qtbot, tmp_path):
    # VB: "The standard Start Screen navigation options will also use your
    # search criteria" — Previous/Next walk the matches, not the whole list.
    names = ["dragon.tga", "dragonfly.tga"] + [f"other{n:02d}.tga" for n in range(10)]
    controller = _controller_with_images(tmp_path, names)
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    dlg._search.setText("dragon")

    matches = dlg._matching_rows()
    assert len(matches) == 2
    assert dlg._list.currentRow() in matches
    dlg._move(1)
    assert dlg._list.currentRow() == matches[1]
    dlg._move(1)  # no third match
    assert dlg._list.currentRow() == matches[1]


def test_escape_closes_the_search_box(qtbot, tmp_path):
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    controller = _controller_with_images(tmp_path, [f"{n:02d}.tga" for n in range(12)])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    dlg._search.setText("05")
    assert dlg._search.text() == "05"

    dlg.eventFilter(
        dlg._search,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
    )
    assert dlg._search.text() == ""


def test_the_preview_edges_navigate_and_the_middle_opens(qtbot, tmp_path):
    controller = _controller_with_images(tmp_path, ["a.tga", "b.tga", "c.tga"])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    dlg.resize(760, 520)
    dlg.show()
    qtbot.waitExposed(dlg)
    dlg._list.setCurrentRow(1)

    assert dlg._zone(5) == -1
    assert dlg._zone(dlg._preview.width() - 5) == 1
    assert dlg._zone(dlg._preview.width() / 2) == 0


def test_the_options_menu_carries_the_documented_entries(qtbot, tmp_path):
    controller = _controller_with_images(tmp_path, ["a.tga"])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    texts = [a.text() for a in dlg._options_btn.menu().actions() if a.text()]
    assert texts == [
        "Auto-Start Screen Selection",
        "Add to Auto Exclusions List",
        "View Information Report",
        "Continuous Slide Show",
        "Slide Show Interval…",
        "Prefixed Start Screens…",
        "Uninstall the Start Screen's Mod",
    ]


def test_the_slideshow_stops_at_the_end_unless_continuous(qtbot, tmp_path):
    controller = _controller_with_images(tmp_path, ["a.tga", "b.tga"])
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)
    dlg._list.setCurrentRow(1)  # the last one

    from PySide6.QtCore import QTimer

    dlg._slideshow_timer = QTimer(dlg)  # pretend it is running
    dlg._slideshow_step()
    assert dlg._slideshow_timer is None, "a non-continuous show stops at the end"

    dlg._settings.slideshow_continuous = True
    dlg._list.setCurrentRow(1)
    dlg._slideshow_timer = QTimer(dlg)
    dlg._slideshow_step()
    assert dlg._list.currentRow() == 0, "a continuous show wraps to the first image"


def test_options_persist_through_the_real_controller(qtbot, tmp_path):
    """The bug this guards: dialogs reached for ``controller.settings``.

    ProfileController has no such attribute — it loads settings on demand via
    ``_settings()`` — so every Options toggle was written to ``None`` and
    silently thrown away. Nothing in the UI said so; the menu simply forgot.
    """
    from vaultkeeper.config.settings import load_settings

    controller = _controller_with_images(
        tmp_path, ["a.tga"], settings_path=tmp_path / "settings.json"
    )
    dlg = StartScreenManager.show_for(controller)
    qtbot.addWidget(dlg)

    assert dlg._settings is not None, "the dialog must find the real settings"
    dlg._auto_action.setChecked(True)
    dlg._store_setting("slideshow_interval", 9)

    reloaded = load_settings(controller._settings_path)
    assert reloaded.auto_loadscreen is True
    assert reloaded.slideshow_interval == 9
