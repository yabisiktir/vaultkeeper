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
    # The status bar's mod-count segment shows installed/total.
    assert win.nit_status.bt_mod_count.text() == "0/2"


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
    # The status bar's info area reports the operation result, and the count updates.
    assert "installed" in win.nit_status.mg_info.text().lower()
    assert win.nit_status.bt_mod_count.text() == "1/2"
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


def test_remove_mod_via_controller(qtbot, controller) -> None:
    # Exercise the controller path the UI action uses (dialog itself is interactive).
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert "Alpha" in controller.pd.mod_keys
    removed = controller.remove_mods(["Alpha"])
    win.refresh()
    assert removed == 1
    assert "Alpha" not in controller.pd.mod_keys
    labels = _all_mod_labels(win)
    assert not any("Alpha" in label for label in labels)


def test_rename_mod_via_controller(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert controller.rename_mod("Alpha", "Alpha Renamed")
    win.refresh()
    assert "Alpha Renamed" in controller.pd.mod_keys
    assert "Alpha" not in controller.pd.mod_keys
    assert any("Alpha Renamed" in label for label in _all_mod_labels(win))


def test_window_has_ribbon_toolbar_and_status_bar(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # The faithful chrome widgets are present.
    assert win.ribbon.count() == 7
    assert "TsInstall" in win.quick_toolbar.actions_by_id
    assert win.nit_status.bt_mods.text() == "Mods:"
    assert not win.windowIcon().isNull()


def test_ribbon_install_action_drives_install(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # Select a mod, then trigger the ribbon's Install/Uninstall button.
    win._tree.setCurrentItem(_find_mod_item(win, "Alpha"))
    win.ribbon.button("RbnInstallUninstall").click()
    assert controller.pd.mod_item("Alpha").installed


def test_unimplemented_command_reports_status(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # A command not wired yet (e.g. the Wizard Builder) reports "not available".
    win._on_command("RbnWizardBuilder")
    assert "not available" in win.nit_status.mg_info.text().lower()


def _find_mod_item(win, name):
    for i in range(win._tree.topLevelItemCount()):
        group = win._tree.topLevelItem(i)
        for j in range(group.childCount()):
            child = group.child(j)
            if name in child.text(0):
                return child
    return None


def test_anneal_command_runs_via_dispatch(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_command("MsAnneal")
    assert "anneal" in win.nit_status.mg_info.text().lower()


def test_select_all_and_collapse_expand(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_command("MsSelectAll")
    assert set(win.selected_mod_names()) == {"Alpha", "Beta"}
    win._on_command("MsCollapseAllGroups")
    assert not win._tree.topLevelItem(0).isExpanded()
    win._on_command("MsExpandAllGroups")
    assert win._tree.topLevelItem(0).isExpanded()


def test_controller_group_operations(qtbot, controller) -> None:
    assert controller.create_group("Campaigns")
    assert not controller.create_group("Campaigns")  # duplicate
    assert "Campaigns" in controller.group_names()
    controller.move_to_group(["Alpha"], "Campaigns")
    assert controller.pd.mod_item("Alpha").group == "Campaigns"
    assert controller.rename_group("Campaigns", "Epics")
    assert controller.pd.mod_item("Alpha").group == "Epics"
    assert "Epics" in controller.group_names()


def test_controller_anneal_persists(qtbot, controller, tmp_path) -> None:
    controller.install(["Alpha"])
    msg = controller.anneal()
    assert "anneal" in msg.lower()
    assert (tmp_path / "Data" / "P.json").exists()


def test_controller_launch_argv_steam_fallback(qtbot, controller) -> None:
    # The tmp game root has no binary, so EE falls back to the Steam URL.
    argv = controller.launch_argv()
    assert any("steam://run/704450" in part for part in argv)


def test_play_command_reports_status(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # Game Saves summary is available and stringy.
    win._on_command("MsGameSaves")
    assert win.nit_status.mg_info.text() != ""


def test_game_exit_records_play_session(qtbot, controller, tmp_path) -> None:
    from datetime import datetime

    # Isolate the game-user dir and drop a synthetic client log there.
    user = tmp_path / "gameuser"
    logs = user / "logs"
    logs.mkdir(parents=True)
    (logs / "nwclientlog1.txt").write_text(
        "\n".join(
            [
                "[Mon Nov 02 17:00:00] Loading Module: Alpha",
                "[Mon Nov 02 17:30:00] Loading Module: Beta",
                "[Mon Nov 02 18:00:00] Server Shutting Down",
            ]
        ),
        encoding="utf-8",
    )
    controller.ctx.game_user_dir = user  # redirect the play loop at the fixture log

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._play_started = datetime(2020, 11, 2, 16, 59)
    win._game_process = object()  # pretend a game was running
    win._on_game_exited()

    # The session was attributed and recorded, and the process state was cleared.
    assert win._game_process is None
    assert "Recorded play time" in win.nit_status.mg_info.text()
    assert controller.play_loop.play_time("Alpha").total_seconds() > 0


def test_game_exit_without_start_is_safe(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._play_started = None
    win._game_process = object()
    win._on_game_exited()  # must not raise
    assert win._game_process is None


def test_selection_populates_detail_panes(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Beta")
    # Details list shows Property/Value rows.
    props = [
        win._details_list.topLevelItem(i).text(0)
        for i in range(win._details_list.topLevelItemCount())
    ]
    assert "Group" in props and "State" in props and "Files" in props
    # Mod-info summary and properties text reflect the selected mod.
    assert "Beta" in win._mod_info.text()
    assert "Beta" in win._details.toPlainText()


def test_deselection_clears_detail_panes(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Beta")
    win._tree.clearSelection()
    win._on_selection_changed()
    assert win._details_list.topLevelItemCount() == 0
    assert win._mod_info.text() == ""
