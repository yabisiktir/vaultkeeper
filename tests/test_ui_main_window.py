"""Headless (offscreen) smoke tests driving the full stack through the UI.

These run under pytest-qt with the offscreen Qt platform, so they construct the
real MainWindow and ProfileController and exercise install/uninstall end-to-end
without a display.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.main_window import MainWindow  # noqa: E402

pytest.importorskip("PySide6")


def _make_mod(profile_mods: Path, name: str, files: dict[str, bytes]) -> None:
    installer = profile_mods / name / C.MOD_INSTALLER_DIR
    for rel, data in files.items():
        target = installer / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    game_root = tmp_path / "NWN"
    _make_mod(profile_mods, "Alpha", {"hak/a.hak": b"AAA"})
    _make_mod(profile_mods, "Beta", {"override/b.2da": b"BBB"})
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
    )


def test_window_populates_from_profile(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # Two mods appear under the default group.
    labels = _all_mod_labels(win)
    assert any("Alpha" in label for label in labels)
    assert any("Beta" in label for label in labels)
    assert "Mods: 2" in win.statusBar().currentMessage()


def test_install_via_ui_updates_state_and_disk(qtbot, controller, tmp_path) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)

    _select_mod(win, "Alpha")
    assert win._act_install.isEnabled()
    win._on_install()

    # The file is physically installed and the state reflects it.
    assert (tmp_path / "NWN" / "hak" / "a.hak").is_file()
    assert controller.pd.mod_item("Alpha").installed
    assert controller.counts() == (2, 1)  # 2 mods, 1 installed
    # The status bar reports the operation result.
    assert "installed" in win.statusBar().currentMessage().lower()
    # Store was saved (on_save wired through the controller).
    assert (tmp_path / "Data" / "P.json").exists()


def test_uninstall_via_ui(qtbot, controller, tmp_path) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    controller.install(["Alpha"])
    win.refresh()

    _select_mod(win, "Alpha")
    win._on_uninstall()
    assert not (tmp_path / "NWN" / "hak" / "a.hak").exists()
    assert not controller.pd.mod_item("Alpha").installed


def test_no_selection_disables_actions(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._tree.clearSelection()
    win._on_selection_changed()
    assert not win._act_install.isEnabled()
    assert not win._act_uninstall.isEnabled()


# -- helpers --------------------------------------------------------------- #
def _all_mod_labels(win: MainWindow) -> list[str]:
    labels = []
    for i in range(win._tree.topLevelItemCount()):
        group = win._tree.topLevelItem(i)
        for j in range(group.childCount()):
            labels.append(group.child(j).text(0))
    return labels


def _select_mod(win: MainWindow, name: str) -> None:
    for i in range(win._tree.topLevelItemCount()):
        group = win._tree.topLevelItem(i)
        for j in range(group.childCount()):
            child = group.child(j)
            if child.text(0).startswith(name):
                child.setSelected(True)
                win._on_selection_changed()
                return


def test_set_controller_repopulates(qtbot, tmp_path) -> None:
    win = MainWindow()  # empty window, no controller
    qtbot.addWidget(win)
    assert win._tree.topLevelItemCount() == 0

    profile_mods = tmp_path / "Profiles" / "P"
    game_root = tmp_path / "NWN"
    _make_mod(profile_mods, "Gamma", {"hak/g.hak": b"GGG"})
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods, game_root=game_root
    )
    win.set_controller(controller)
    assert any("Gamma" in label for label in _all_mod_labels(win))


def test_contents_pane_shows_mod_files(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Beta")  # ships override/b.2da
    # The contents pane lists the file grouped under its folder.
    contents = win._contents
    folders = [contents.topLevelItem(i).text(0) for i in range(contents.topLevelItemCount())]
    assert "override" in folders


def test_empty_window_shows_guidance(qtbot) -> None:
    win = MainWindow()  # no controller
    qtbot.addWidget(win)
    assert "Set Up Profile" in win._details.toPlainText()
