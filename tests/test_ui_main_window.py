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


def test_title_bar_shows_played_mod_and_location(qtbot, tmp_path) -> None:
    # VB TitleInfo: "Vaultkeeper — <mod currently being played> (<save location>)",
    # both from the current game save; "Vaultkeeper" when nothing is saved.
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    user_dir = tmp_path / "user"
    # A current save: folder starts with a 6-digit number; the .sav stem is the
    # game/mod name; savenfo.txt holds the in-module location.
    save = user_dir / "saves" / "000001 - Quicksave"
    save.mkdir(parents=True)
    (save / "Bloodright.sav").write_bytes(b"S")
    (save / "savenfo.txt").write_text("Temple of Dergarion")
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=user_dir,
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # The play loop exists once the user plays / opens game saves; building it and
    # refreshing surfaces the current save in the title (VB TitleInfo at load).
    assert controller.play_loop is not None
    win.refresh()
    assert win.windowTitle() == "Vaultkeeper — Bloodright (Temple of Dergarion)"


def test_title_bar_plain_when_no_saves(qtbot, tmp_path) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=tmp_path / "user",  # no saves
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert controller.play_loop is not None  # build the loop; still no saves
    win.refresh()
    assert win.windowTitle() == "Vaultkeeper"


def test_status_bar_shows_group_counts(qtbot, controller) -> None:
    # VB NitUserInterface.DisplayGroupModCounts: the status-bar Group segment shows
    # the selected mods' shared group + (installed/total), blank across groups.
    win = MainWindow(controller)
    qtbot.addWidget(win)

    win._update_group_status([])
    assert win.nit_status.bt_group.text() == "None"

    # Alpha + Beta are scanned into the hidden "No Group" bucket → reads "None"
    # (VB Co.None for a hidden group), with the group's (installed/total) count.
    _select_mod(win, "Alpha")
    assert win.nit_status.bt_group.text() == "None (0/2)"

    # Installing Alpha bumps the group's installed count.
    win._on_install()
    _select_mod(win, "Alpha")
    assert win.nit_status.bt_group.text() == "None (1/2)"

    # A named (non-hidden) group shows its own name, not "None".
    controller.pd.mod_item("Beta").group = "Campaigns"
    win.refresh()
    _select_mod(win, "Beta")
    assert win.nit_status.bt_group.text() == "Campaigns (0/1)"


def _grouped_controller(tmp_path):
    from vaultkeeper.core.mod_data import ModData
    from vaultkeeper.core.profile_data import ProfileData
    from vaultkeeper.persistence.profile_store import save_profile

    pd = ProfileData()
    pd.add_mod(ModData(group="Adventures", mod_name="A"))
    pd.add_mod(ModData(group="Adventures", mod_name="B"))
    pd.add_mod(ModData(group="Campaigns", mod_name="C"))
    pd.add_mod(ModData(group="Adventures"))  # explicit group row
    pd.initialise_groups()
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
        game_user_dir=tmp_path / "user",
    )


def test_delete_group_via_ui(qtbot, tmp_path) -> None:
    # VB DeleteSelectedGroups, offered via the group-header right-click menu.
    ctrl = _grouped_controller(tmp_path)
    win = MainWindow(ctrl)
    qtbot.addWidget(win)
    win._confirm = lambda *a, **k: True  # accept the confirmation
    win._on_delete_groups(["Adventures"])
    assert ctrl.pd.mod_keys == ["C"]
    assert "Adventures" not in ctrl.group_names()


def test_rename_group_via_ui(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    ctrl = _grouped_controller(tmp_path)
    win = MainWindow(ctrl)
    qtbot.addWidget(win)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Epics", True))
    win._on_rename_group("Adventures")
    assert "Epics" in ctrl.group_names()
    assert "Adventures" not in ctrl.group_names()
    assert set(ctrl.group_member_names("Epics")) == {"A", "B"}


def test_f2_renames_the_current_group(qtbot, tmp_path, monkeypatch) -> None:
    """renameagroup.htm: "Select the Group … Press F2 or click Rename"."""
    from PySide6.QtWidgets import QInputDialog

    ctrl = _grouped_controller(tmp_path)
    win = MainWindow(ctrl)
    qtbot.addWidget(win)

    # Make the "Adventures" header the current row (headers are not selectable).
    tree = win._tree
    for i in range(tree.topLevelItemCount()):
        if tree.topLevelItem(i).text(0) == "Adventures":
            tree.setCurrentItem(tree.topLevelItem(i))
            break
    assert win._tree.current_group_name() == "Adventures"
    assert win.selected_mod_names() == []  # nothing is selected, only current

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Epics", True))
    win._on_rename()  # the F2 handler
    assert "Epics" in ctrl.group_names()
    assert "Adventures" not in ctrl.group_names()


def test_f2_on_a_mod_still_renames_the_mod(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    ctrl = _grouped_controller(tmp_path)
    win = MainWindow(ctrl)
    qtbot.addWidget(win)
    win._tree.select_mod("A")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("A2", True))
    win._on_rename()
    assert ctrl.pd.mod_item("A2") is not None
    assert ctrl.pd.mod_item("A") is None


def test_delete_removes_the_current_group(qtbot, tmp_path, monkeypatch) -> None:
    """removegroups.htm: "Select … Groups … Press Delete or click Delete"."""
    ctrl = _grouped_controller(tmp_path)
    win = MainWindow(ctrl)
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "_confirm", lambda *a, **k: True)

    tree = win._tree
    for i in range(tree.topLevelItemCount()):
        if tree.topLevelItem(i).text(0) == "Adventures":
            tree.setCurrentItem(tree.topLevelItem(i))
            break
    assert win._tree.current_group_name() == "Adventures"

    win._on_remove()  # the Delete handler
    assert "Adventures" not in ctrl.group_names()


def test_delete_key_emits_on_a_group_header(qtbot, tmp_path, monkeypatch) -> None:
    ctrl = _grouped_controller(tmp_path)
    win = MainWindow(ctrl)
    qtbot.addWidget(win)
    # The real _on_remove is connected to the signal; keep its confirm dialog
    # from opening (this test only checks the key reaches the signal).
    monkeypatch.setattr(win, "_confirm", lambda *a, **k: False)
    tree = win._tree
    for i in range(tree.topLevelItemCount()):
        if tree.topLevelItem(i).text(0) == "Adventures":
            tree.setCurrentItem(tree.topLevelItem(i))
            break

    fired = []
    tree.delete_requested.connect(lambda: fired.append(True))
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
    tree.keyPressEvent(event)
    assert fired == [True]


def test_group_header_context_menu_target(qtbot, tmp_path) -> None:
    # A group header is detected for the group menu; a mod row is not.
    ctrl = _grouped_controller(tmp_path)
    win = MainWindow(ctrl)
    qtbot.addWidget(win)
    tree = win._tree
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        if item.text(0) == "Adventures":
            rect = tree.visualItemRect(item)
            assert tree.group_header_at(rect.center()) == "Adventures"
            # A child mod row is not a group header.
            child_rect = tree.visualItemRect(item.child(0))
            assert tree.group_header_at(child_rect.center()) is None
            return
    raise AssertionError("Adventures header not found")


def test_mod_selector_populates_and_selects(qtbot, controller) -> None:
    # VB TsbModSelector (menu-bar right): a type-to-find combo bound to the mod
    # list that selects the chosen mod (ItemSelected → SelectMod).
    win = MainWindow(controller)
    qtbot.addWidget(win)
    items = [win._mod_selector.itemText(i) for i in range(win._mod_selector.count())]
    assert "Alpha" in items and "Beta" in items
    # It starts blank (a cue, not a pre-selection) and doesn't select on populate.
    assert win._mod_selector.currentText() == ""
    assert win.selected_mod_names() == []
    # Choosing an entry selects that mod in the tree.
    win._mod_selector.setCurrentText("Beta")
    win._on_mod_selector_activated(0)
    assert win.selected_mod_names() == ["Beta"]


def test_play_tab_install_button_toggles(qtbot, controller) -> None:
    # VB NIT.ModView.SetInstallAvailability: the Play-tab combined button reflects
    # Install vs Uninstall, pluralizes, and hides when neither applies.
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.show()
    button = win.ribbon.button("RbnInstallUninstall")

    # Nothing selected → button hidden, both menu actions disabled.
    win._on_selection_changed([])
    assert not button.isVisible()
    assert not win._act_install.isEnabled()
    assert not win._act_uninstall.isEnabled()

    # A not-yet-installed mod (has an installer) → "Install\nSelected Mod".
    _select_mod(win, "Alpha")
    assert button.isVisible()
    assert button.text() == "Install\nSelected Mod"
    assert win._act_install.isEnabled() and not win._act_uninstall.isEnabled()
    assert win.quick_toolbar.actions_by_id["TsInstall"].isVisible()
    assert not win.quick_toolbar.actions_by_id["TsUninstall"].isVisible()

    # After installing it → "Uninstall\nSelected Mod".
    win._on_install()
    _select_mod(win, "Alpha")  # install refreshes the tree, clearing selection
    assert button.text() == "Uninstall\nSelected Mod"
    assert win._act_uninstall.isEnabled() and not win._act_install.isEnabled()
    assert win.quick_toolbar.actions_by_id["TsUninstall"].isVisible()
    assert not win.quick_toolbar.actions_by_id["TsInstall"].isVisible()

    # Multi-selecting both mods pluralizes the caption.
    win._tree.clearSelection()
    for item in _mod_items(win):
        if item.text(0).startswith(("Alpha", "Beta")):
            item.setSelected(True)
    win._on_selection_changed()
    assert button.text().endswith("Selected Mods")


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
def _mod_items(win: MainWindow):
    """Every mod row — top-level (hidden "No Group") or under a group header."""
    tree = win._tree
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        if item.childCount() == 0:
            yield item  # a top-level mod (ungrouped)
        else:
            for j in range(item.childCount()):
                yield item.child(j)


def _all_mod_labels(win: MainWindow) -> list[str]:
    return [item.text(0) for item in _mod_items(win)]


def _select_mod(win: MainWindow, name: str) -> None:
    # Emulate a single click: clear any prior selection first so exactly one
    # mod is selected (otherwise the multi-select branch clears the panes).
    win._tree.clearSelection()
    for item in _mod_items(win):
        if item.text(0).startswith(name):
            item.setSelected(True)
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
    text = win._details.toPlainText()
    # Guidance must name a menu path that actually exists (File ▸ Load Profile).
    assert "Load Profile" in text
    assert win.nit_menu.action("MsLoadProfile") is not None


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
    # A command not wired yet reports "not available" rather than doing nothing.
    # MsConnect is a recorded non-goal (the Shared NIT Store), so it stays unwired.
    win._on_command("MsConnect")
    assert "not available" in win.nit_status.mg_info.text().lower()


def test_help_menu_opens_topic(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # A Help-menu topic id opens the help viewer at the matching <name>.htm.
    win._on_command("MsGetStarted")
    viewer = win._help_viewer
    qtbot.addWidget(viewer)
    assert viewer.contents.topLevelItemCount() > 0
    assert "msgetstarted.htm" in viewer.browser.source().toString().lower()

    # View Help opens the contents root.
    win._on_command("MsViewHelp")
    qtbot.addWidget(win._help_viewer)
    assert win._help_viewer.contents.topLevelItemCount() > 0


def _find_mod_item(win, name):
    for item in _mod_items(win):
        if name in item.text(0):
            return item
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
    # The window installs the modal Qt prompter; swap in the non-interactive
    # default so headless exit-processing falls back to the raw log name
    # (Alpha -> Alpha) instead of blocking on a dialog.
    from vaultkeeper.game.game_mapper import DefaultPrompter

    controller.play_prompter = DefaultPrompter()
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
    # Mod-info summary reflects the selected mod.
    assert "Beta" in win._mod_info.text()
    # The _details pane is the editable notes editor; Beta has no notes yet.
    assert win._details.toPlainText() == ""


def test_deselection_clears_detail_panes(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Beta")
    win._tree.clearSelection()
    win._on_selection_changed()
    assert win._details_list.topLevelItemCount() == 0
    assert win._mod_info.text() == ""


def test_notes_edit_and_persist(qtbot, controller, monkeypatch) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # Confirm-saves defaults on (VB BehaviourConfirmSaves), so switching away with
    # edited notes prompts; accept the save.
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    _select_mod(win, "Alpha")
    # Type a note and switch selection -> it is saved to the mod's RTF.
    # (setPlainText alone doesn't set the modified flag; a real keypress does,
    # so mark it modified to emulate the user having typed.)
    win._details.setPlainText("Great module. Finished chapter 3.")
    win._details.document().setModified(True)
    _select_mod(win, "Beta")
    assert controller.read_notes("Alpha") == "Great module. Finished chapter 3."
    # Re-selecting reloads the saved note.
    _select_mod(win, "Alpha")
    assert win._details.toPlainText() == "Great module. Finished chapter 3."


def test_notes_round_trip_via_controller(qtbot, controller) -> None:
    controller.save_notes("Alpha", "Line one\nLine two")
    assert controller.read_notes("Alpha") == "Line one\nLine two"
    assert controller.mod_notes_path("Alpha").name == "Alpha.rtf"
    # Clearing notes removes the file.
    controller.save_notes("Alpha", "")
    assert not controller.mod_notes_path("Alpha").exists()


def test_update_downloads_command_moves_archives(qtbot, controller, tmp_path) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    mod_folder = tmp_path / "Profiles" / "P" / "Alpha"
    (mod_folder / "download.zip").write_bytes(b"ZIP")

    _select_mod(win, "Alpha")
    win._on_command("MsUpdateDownloads")

    assert (mod_folder / C.DOWNLOADS_DIR / "download.zip").is_file()
    assert not (mod_folder / "download.zip").exists()
    assert "moved: 1" in win.nit_status.mg_info.text().lower()


def test_compact_command_is_safe(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    win._on_command("MsCompact")  # must not raise; reports a status
    assert win.nit_status.mg_info.text() != ""


def test_character_command_opens_viewer(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_command("MsCharacterExplorer")  # must not raise; opens the viewer
    assert win._character_viewer is not None


def test_portrait_command_opens_manager(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_command("MsPortraitManager")  # must not raise
    assert win._portrait_manager is not None


def test_publish_command_wired(qtbot, controller, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.core import constants as C
    from vaultkeeper.core.archive import FakeArchiveExtractor
    from vaultkeeper.ui.dialogs.publish_mod import PublishMod

    controller._extractor = FakeArchiveExtractor()
    win = MainWindow(controller)
    qtbot.addWidget(win)

    # The command opens the (modal) PublishMod dialog; drive the publish without
    # actually blocking on exec(), and silence its result message box.
    opened: dict[str, str] = {}

    def fake_exec(self) -> int:
        opened["mod"] = self._mod_name
        self._on_publish()
        return 0

    monkeypatch.setattr(PublishMod, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    _select_mod(win, "Alpha")
    win._on_command("MsPublishMod")

    assert opened["mod"] == "Alpha"
    published = controller.ctx.profile_mods_dir / "Alpha" / C.PUBLISHED_DIR / "Alpha.7z"
    assert published.is_file()


def test_user_response_editor_command_wired(qtbot, controller, tmp_path) -> None:
    controller.ctx.game_user_dir = tmp_path / "gameuser"
    (controller.ctx.game_user_dir / "saves").mkdir(parents=True)
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_command("DbGameMapUserReport")  # must not raise
    assert win._user_response_editor is not None


# -- Contents pane: view + delete a file (VB CmContents) ------------------- #
def _select_contents_file(win: MainWindow, folder_name: str, file_name: str):
    tree = win._contents
    for i in range(tree.topLevelItemCount()):
        folder = tree.topLevelItem(i)
        if folder.text(0) == folder_name:
            for j in range(folder.childCount()):
                child = folder.child(j)
                if child.text(0) == file_name:
                    tree.setCurrentItem(child)
                    return child
    return None


def test_controller_mod_file_path_and_delete(controller, tmp_path) -> None:
    path = controller.mod_file_path("Alpha", "hak", "a.hak")
    assert path is not None and path.is_file()
    assert controller.mod_file_path("Alpha", "hak", "missing.hak") is None
    # Delete drops the file and its FileKey; a second delete is a no-op.
    assert controller.delete_mod_file("Alpha", "hak", "a.hak")
    assert controller.mod_file_path("Alpha", "hak", "a.hak") is None
    assert not any(fk.filename == "a.hak" for fk in controller.pd.mod_item("Alpha").files)
    assert not controller.delete_mod_file("Alpha", "hak", "a.hak")


def test_contents_view_carries_file_key(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    item = _select_contents_file(win, "hak", "a.hak")
    assert item is not None
    assert win._contents.selected_file() == ("hak", "a.hak")


def test_contents_double_click_opens_viewer(qtbot, controller, monkeypatch) -> None:
    from vaultkeeper.ui.dialogs.text_viewer import TextViewer

    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    _select_contents_file(win, "hak", "a.hak")

    calls: dict = {}
    monkeypatch.setattr(
        TextViewer, "show_file", lambda path, title, parent: calls.setdefault("path", path)
    )
    win._on_view_contents_file()
    assert str(calls["path"]).endswith("a.hak")


def test_contents_delete_file_via_ui(qtbot, controller, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    _select_contents_file(win, "hak", "a.hak")

    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    win._on_delete_contents_file()
    installer = tmp_path / "Profiles" / "P" / "Alpha" / C.MOD_INSTALLER_DIR
    assert not (installer / "hak" / "a.hak").is_file()
    assert not any(fk.filename == "a.hak" for fk in controller.pd.mod_item("Alpha").files)


# -- Command availability: unimplemented chrome is greyed out -------------- #
def test_unimplemented_commands_are_disabled(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    implemented = win.implemented_commands()

    # Faithful-but-unwired items exist (parity) but are disabled everywhere.
    # The Shared NIT Store commands are recorded non-goals, so they stay unwired.
    for dead_id in ("MsConnect", "MsOpenSharedStore", "MsSynchroniseMods"):
        act = win.nit_menu.action(dead_id)
        assert act is not None and not act.isEnabled()
        assert dead_id not in implemented
    # No ribbon button is dead any more. RbnDisplaySettings was the last one, and
    # it only became wireable once MsDisplaySettings had a handler — the two are
    # the same command, so a greyed button beside a working menu item is never
    # the honest state, it is a gap.
    assert win.ribbon.button("RbnDisplaySettings").isEnabled()
    # RbnExportSettings and RbnManageWorkshop used to be listed above: ribbon
    # buttons with no handler, which looked like parity and behaved like dead
    # controls while the same screen worked from the menu. Both are wired now —
    # and this assertion is why the change had to be made deliberately rather
    # than being absorbed as "a test broke".
    for wired in ("RbnExportSettings", "RbnManageWorkshop"):
        assert wired in implemented
        assert win.ribbon.button(wired).isEnabled()
    # The quick toolbar's commands are now all wired (cut/copy/paste were the last
    # dead ones), so every toolbar id is implemented.
    assert all(tid in implemented for tid in win.quick_toolbar.actions_by_id)

    # Implemented items are untouched by the pass (still governed by selection
    # logic or enabled by default).
    assert win.nit_menu.action("MsNewMod").isEnabled()
    assert win.ribbon.button("RbnPlay").isEnabled()
    assert win.quick_toolbar.actions_by_id["TsNewMod"].isEnabled()
    # The handled visibility toggles stay live.
    assert win.nit_menu.action("MsShowRibbon").isEnabled()
    # Unhandled checkable toggles are disabled like any other dead item.
    assert not win.nit_menu.action("MsDebugOptionsMenu").isEnabled()


def test_implemented_commands_match_dispatch(qtbot, controller) -> None:
    # Every dispatchable id is reported implemented (single source of truth).
    win = MainWindow(controller)
    qtbot.addWidget(win)
    implemented = win.implemented_commands()
    assert set(win._command_handlers()) <= implemented


def test_newly_wired_commands_are_enabled(qtbot, controller) -> None:
    # Font/theme, About, Send Feedback, Convert Restorer, Recover Groups/Properties
    # are now wired (the availability pass enables anything with a handler).
    win = MainWindow(controller)
    qtbot.addWidget(win)
    for command_id in (
        "MsFontAndColour",
        "MsAbout",
        "MsSendFeedback",
        "MsConvertRestorer",
        "MsRecoverGroups",
        "MsRecoverModProperties",
    ):
        act = win.nit_menu.action(command_id)
        assert act is not None and act.isEnabled(), command_id
    assert win.ribbon.button("RbnFontAndColour").isEnabled()


def test_basic_and_advanced_settings_are_distinct_dialogs(
    qtbot, controller, monkeypatch
) -> None:
    # VB has two distinct surfaces: the curated BasicSettings dialog and the full
    # per-preference Settings browser. MsBasicSettings must open the former.
    from vaultkeeper.ui.dialogs.basic_settings import BasicSettingsDialog
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    win = MainWindow(controller)
    qtbot.addWidget(win)
    seen = {"basic": 0, "advanced": 0}

    def fake_basic_edit(settings_path=None, parent=None):
        seen["basic"] += 1
        return None, False  # cancelled, no advanced chain

    def fake_advanced_edit(settings_path=None, parent=None, *, controller=None, start_tab=""):
        seen["advanced"] += 1
        return None

    monkeypatch.setattr(BasicSettingsDialog, "edit", staticmethod(fake_basic_edit))
    monkeypatch.setattr(SettingsDialog, "edit", staticmethod(fake_advanced_edit))

    win._on_command("MsBasicSettings")
    assert seen == {"basic": 1, "advanced": 0}
    win._on_command("MsSettings")
    assert seen == {"basic": 1, "advanced": 1}


def test_basic_settings_advanced_button_chains_to_full_settings(
    qtbot, controller, monkeypatch
) -> None:
    from vaultkeeper.ui.dialogs.basic_settings import BasicSettingsDialog
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    win = MainWindow(controller)
    qtbot.addWidget(win)
    seen = {"advanced": 0}

    def fake_basic_edit(settings_path=None, parent=None):
        from vaultkeeper.config.settings import Settings

        return Settings(), True  # saved + Advanced requested

    def fake_advanced_edit(settings_path=None, parent=None, *, controller=None, start_tab=""):
        seen["advanced"] += 1
        return None

    monkeypatch.setattr(BasicSettingsDialog, "edit", staticmethod(fake_basic_edit))
    monkeypatch.setattr(SettingsDialog, "edit", staticmethod(fake_advanced_edit))

    win._on_command("MsBasicSettings")
    assert seen["advanced"] == 1  # Advanced button chained into full Settings


# -- Web link: edit + copy (VB MsEditWebLink / MsCopyWebLink) --------------- #
def test_controller_set_and_get_web_link(controller) -> None:
    assert controller.mod_web_link("Alpha") == ""
    ok = controller.set_mod_web_link("Alpha", "https://neverwintervault.org/x")
    assert ok["ok"] and controller.mod_web_link("Alpha") == "https://neverwintervault.org/x"
    # Invalid URL is rejected, link unchanged.
    bad = controller.set_mod_web_link("Alpha", "not a url")
    assert not bad["ok"] and "valid web page" in bad["message"]
    assert controller.mod_web_link("Alpha") == "https://neverwintervault.org/x"
    # Empty clears it.
    assert controller.set_mod_web_link("Alpha", "")["ok"]
    assert controller.mod_web_link("Alpha") == ""


def test_edit_web_link_via_ui(qtbot, controller, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    # The command is now enabled (it has a handler).
    assert win.nit_menu.action("MsEditWebLink").isEnabled()
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *a, **k: ("www.example.com", True)
    )
    win._on_command("MsEditWebLink")
    assert controller.mod_web_link("Alpha") == "www.example.com"


def test_copy_web_link_via_ui(qtbot, controller) -> None:
    from PySide6.QtWidgets import QApplication

    controller.set_mod_web_link("Beta", "https://example.com/beta")
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Beta")
    win._on_command("MsCopyWebLink")
    assert QApplication.clipboard().text() == "https://example.com/beta"


# -- Copy Name (VB MsCopyName) --------------------------------------------- #
def test_copy_name_via_ui(qtbot, controller) -> None:
    from PySide6.QtWidgets import QApplication

    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    win._on_command("MsCopyName")
    assert QApplication.clipboard().text() == "Alpha"
    assert win.nit_menu.action("MsCopyName").isEnabled()  # wired -> enabled


def test_copy_contents_file_name(qtbot, controller) -> None:
    from PySide6.QtWidgets import QApplication

    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    _select_contents_file(win, "hak", "a.hak")
    win._on_copy_contents_name()
    assert QApplication.clipboard().text() == "a.hak"


# -- Display Info: character / image preview (VB MsDisplayInfo) ------------- #
def _tga_bytes(w: int = 2, h: int = 2) -> bytes:
    import struct

    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 24, 0)
    return header + bytes([0, 0, 255] * (w * h))


def _image_controller(tmp_path):
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(profile_mods, "Art", {"portraits/p.tga": _tga_bytes(), "hak/big.hak": b"X"})
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_display_info_opens_image_viewer(qtbot, tmp_path) -> None:
    from vaultkeeper.ui.dialogs.image_viewer import ImageViewer

    win = MainWindow(_image_controller(tmp_path))
    qtbot.addWidget(win)
    _select_mod(win, "Art")
    _select_contents_file(win, "portraits", "p.tga")
    win._on_display_contents_info()
    assert isinstance(win._image_viewer, ImageViewer)


def test_display_info_bic_opens_character(qtbot, tmp_path, monkeypatch) -> None:
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(profile_mods, "Chars", {"bic/hero.bic": b"not-a-real-bic"})
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Chars")
    _select_contents_file(win, "bic", "hero.bic")
    seen = {}
    monkeypatch.setattr(
        MainWindow, "_show_character_file", lambda self, path: seen.setdefault("p", path)
    )
    win._on_display_contents_info()
    assert str(seen["p"]).endswith("hero.bic")


def test_display_info_other_falls_back_to_text(qtbot, tmp_path, monkeypatch) -> None:
    from vaultkeeper.ui.dialogs.text_viewer import TextViewer

    win = MainWindow(_image_controller(tmp_path))
    qtbot.addWidget(win)
    _select_mod(win, "Art")
    _select_contents_file(win, "hak", "big.hak")
    calls = {}
    monkeypatch.setattr(
        TextViewer, "show_file", lambda path, title, parent: calls.setdefault("p", path)
    )
    win._on_display_contents_info()
    assert str(calls["p"]).endswith("big.hak")


def test_image_viewer_load_pixmap(tmp_path) -> None:
    from vaultkeeper.ui.dialogs.image_viewer import load_pixmap

    tga = tmp_path / "x.tga"
    tga.write_bytes(_tga_bytes(4, 4))
    pix = load_pixmap(tga)
    assert pix is not None and not pix.isNull()
    assert load_pixmap(tmp_path / "missing.tga") is None


# -- Add Mods from Files (VB MsAddMods / ModPaste) ------------------------- #
def test_add_mods_from_files(controller, tmp_path) -> None:
    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller._extractor = FakeArchiveExtractor(
        contents={"cool.zip": {"hak/c.hak": b"CCC", "readme.txt": b"hi"}}
    )
    result = controller.add_mods_from_files([tmp_path / "cool.zip"], group="100. Packs")
    assert result["created"] == ["cool"]
    md = controller.pd.mod_item("cool")
    assert md is not None and md.group == "100. Packs"
    mod_dir = controller.ctx.profile_mods_dir / "cool"
    assert (mod_dir / "hak" / "c.hak").is_file()
    assert (mod_dir / "_Downloads").is_dir()

    # A non-archive errors; an already-created name is ignored.
    r2 = controller.add_mods_from_files(
        [tmp_path / "notes.txt", tmp_path / "cool.zip"]
    )
    assert r2["errors"] == ["notes.txt"] and r2["ignored"] == ["cool"]
    assert not r2["created"]


def test_add_mods_from_files_extract_failure_cleans_up(controller, tmp_path) -> None:
    from vaultkeeper.core.archive import FakeArchiveExtractor

    # available=False -> extract returns not-ok; the half-made mod dir is removed.
    controller._extractor = FakeArchiveExtractor(available=False)
    result = controller.add_mods_from_files([tmp_path / "broken.zip"])
    assert result["errors"] == ["broken.zip"] and not result["created"]
    assert controller.pd.mod_item("broken") is None
    assert not (controller.ctx.profile_mods_dir / "broken").exists()


def test_add_mods_via_ui(qtbot, controller, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    from vaultkeeper.core.archive import FakeArchiveExtractor

    controller._extractor = FakeArchiveExtractor(
        contents={"newmod.7z": {"override/o.2da": b"X"}}
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # New mods land in the selected mod's group.
    _select_mod(win, "Alpha")
    group = controller.pd.mod_item("Alpha").group
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *a, **k: ([str(tmp_path / "newmod.7z")], ""),
    )
    win._on_command("MsAddMods")
    md = controller.pd.mod_item("newmod")
    assert md is not None and md.group == group
    assert win.nit_menu.action("MsAddMods").isEnabled()


# -- Contents file Cut/Copy/Paste between mods (VB CmContents) -------------- #
def test_controller_copy_mod_file(controller, tmp_path) -> None:
    # Copy Alpha's hak/a.hak into Beta.
    ok = controller.copy_mod_file("Alpha", "hak", "a.hak", "Beta")
    assert ok
    beta_file = (
        tmp_path / "Profiles" / "P" / "Beta" / C.MOD_INSTALLER_DIR / "hak" / "a.hak"
    )
    assert beta_file.is_file()
    assert any(fk.filename == "a.hak" for fk in controller.pd.mod_item("Beta").files)
    # Source is untouched by a copy.
    assert controller.mod_file_path("Alpha", "hak", "a.hak") is not None
    # Pasting onto the same file is rejected.
    assert not controller.copy_mod_file("Beta", "hak", "a.hak", "Beta")


def test_controller_move_mod_file(controller) -> None:
    ok = controller.copy_mod_file("Alpha", "hak", "a.hak", "Beta", move=True)
    assert ok
    assert any(fk.filename == "a.hak" for fk in controller.pd.mod_item("Beta").files)
    # Move deletes the source.
    assert controller.mod_file_path("Alpha", "hak", "a.hak") is None


def test_contents_copy_paste_via_ui(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    _select_contents_file(win, "hak", "a.hak")
    win._on_copy_contents_file(cut=False)
    assert win._file_clipboard[0] == "Alpha" and win._file_clipboard[3] is False
    # Switch to Beta and paste.
    _select_mod(win, "Beta")
    win._on_paste_contents_file()
    assert any(fk.filename == "a.hak" for fk in controller.pd.mod_item("Beta").files)
    # A copy keeps the clipboard for repeated pastes.
    assert win._file_clipboard is not None


def test_contents_cut_paste_clears_clipboard(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")
    _select_contents_file(win, "hak", "a.hak")
    win._on_copy_contents_file(cut=True)
    _select_mod(win, "Beta")
    win._on_paste_contents_file()
    assert controller.mod_file_path("Alpha", "hak", "a.hak") is None  # moved
    assert win._file_clipboard is None  # cut consumed


# -- Find Files in Profile (VB FindProfileFilesDialogue) ------------------- #
def test_find_profile_files(controller) -> None:
    # Fixture mods: Alpha has hak/a.hak, Beta has override/b.2da.
    assert controller.find_profile_files("")["count"] == 0  # empty query -> nothing
    hak = controller.find_profile_files("a.hak")
    assert hak["count"] == 1
    assert hak["rows"][0] == {"mod": "Alpha", "filename": "a.hak", "folder": "hak"}
    # Substring across mods, sorted by mod then file.
    dot = controller.find_profile_files(".")
    mods = [r["mod"] for r in dot["rows"]]
    assert mods == ["Alpha", "Beta"]
    # Match-case + whole-word.
    assert controller.find_profile_files("A.HAK")["count"] == 1  # default insensitive
    assert controller.find_profile_files("A.HAK", match_case=True)["count"] == 0
    assert controller.find_profile_files("ha")["count"] == 1
    assert controller.find_profile_files("ha", whole_word=True)["count"] == 0


def test_find_dialog_and_select(qtbot, controller) -> None:
    from vaultkeeper.ui.dialogs.find_files import FindFilesDialog

    picked = {}
    dlg = FindFilesDialog(controller, on_select=lambda m: picked.setdefault("mod", m))
    qtbot.addWidget(dlg)
    dlg._find.setText("b.2da")
    assert dlg._results.topLevelItemCount() == 1
    assert dlg._results.topLevelItem(0).text(0) == "Beta"
    assert "Files Found: 1" in dlg._count.text()
    assert dlg._select_btn.isEnabled()
    dlg._select()
    assert picked["mod"] == "Beta"


def test_find_selects_mod_in_tree(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._tree.clearSelection()
    win._select_mod_by_name("Beta")
    assert win.selected_mod_names() == ["Beta"]
    # Wired -> the command is enabled.
    assert win.nit_menu.action("MsFind").isEnabled()


# -- Go to Group (VB MsGoToGroup) ------------------------------------------ #
def test_go_to_group_selects_group(qtbot, controller) -> None:
    from PySide6.QtWidgets import QInputDialog

    # Put Alpha in a named group so a header row exists.
    controller.move_to_group(["Alpha"], "100. Packs")
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._tree.clearSelection()
    # select_group expands + selects the group's first mod.
    assert win._tree.select_group("100. Packs")
    assert "Alpha" in win.selected_mod_names()

    # The command dispatches through a group picker.
    import unittest.mock as m

    with m.patch.object(QInputDialog, "getItem", return_value=("100. Packs", True)):
        win._tree.clearSelection()
        win._on_command("MsGoToGroup")
    assert "Alpha" in win.selected_mod_names()
    assert win.nit_menu.action("MsGoToGroup").isEnabled()


# -- double-click a mod to install it (VB FvMods_MouseDoubleClick) ------------- #
def _first_mod_item(win, name: str):
    for index in range(win._tree.topLevelItemCount()):
        item = win._tree.topLevelItem(index)
        if win._tree.mod_name_of(item) == name:
            return item
        for child in range(item.childCount()):
            kid = item.child(child)
            if win._tree.mod_name_of(kid) == name:
                return kid
    raise AssertionError(f"{name} is not in the tree")


def test_double_clicking_a_mod_installs_it(qtbot, controller) -> None:
    """The everyday interaction the port had never had."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.refresh()
    item = _first_mod_item(win, "Alpha")
    win._tree.setCurrentItem(item)
    assert not controller.pd.mod_item("Alpha").installed

    win._on_mod_double_clicked(item)
    assert controller.pd.mod_item("Alpha").installed


def test_double_clicking_an_installed_mod_uninstalls_it(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.refresh()
    item = _first_mod_item(win, "Alpha")
    win._tree.setCurrentItem(item)
    win._on_mod_double_clicked(item)
    assert controller.pd.mod_item("Alpha").installed

    item = _first_mod_item(win, "Alpha")   # the tree was rebuilt by the install
    win._tree.setCurrentItem(item)
    win._on_mod_double_clicked(item)
    assert not controller.pd.mod_item("Alpha").installed


def test_double_clicking_a_group_header_does_not_install(qtbot, controller) -> None:
    """Groups expand and collapse, which is what VB's DoubleClickAction guard does."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.refresh()
    header = None
    for index in range(win._tree.topLevelItemCount()):
        candidate = win._tree.topLevelItem(index)
        if not win._tree.mod_name_of(candidate) and candidate.childCount():
            header = candidate
            break
    if header is None:
        pytest.skip("this fixture has no grouped mods")
    before = {n: controller.pd.mod_item(n).installed for n in ("Alpha", "Beta")}
    win._on_mod_double_clicked(header)
    assert {n: controller.pd.mod_item(n).installed for n in ("Alpha", "Beta")} == before


def test_double_click_never_does_what_the_buttons_refuse(qtbot, controller) -> None:
    """It asks the same question the toolbar does, so the two cannot disagree."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.refresh()
    item = _first_mod_item(win, "Alpha")
    win._tree.setCurrentItem(item)
    win._act_install.setEnabled(False)
    win._act_uninstall.setEnabled(False)
    win._on_mod_double_clicked(item)
    assert not controller.pd.mod_item("Alpha").installed


# -- Options-menu housekeeping (VB Options menu) ------------------------------- #
def test_the_options_housekeeping_commands_are_live(qtbot, controller) -> None:
    """All three were greyed as "not yet available" while doing nothing more
    than resetting local state."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    implemented = win.implemented_commands()
    for command in ("MsResetWindow", "MsClearWaitCursors", "MsClearSelectionHistory"):
        assert command in implemented
        assert win.nit_menu.action(command).isEnabled()


def test_clearing_wait_cursors_releases_a_stuck_one(qtbot, controller) -> None:
    """An override cursor outliving its work makes the app look hung."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    win = MainWindow(controller)
    qtbot.addWidget(win)
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    win._on_clear_wait_cursors()
    assert QApplication.overrideCursor() is None
    assert "Cleared 2" in win.nit_status.mg_info.text()


def test_clearing_wait_cursors_with_none_set_says_so(qtbot, controller) -> None:
    from PySide6.QtWidgets import QApplication

    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_clear_wait_cursors()
    assert "No wait cursor" in win.nit_status.mg_info.text()


def test_clearing_selection_history_forgets_contents_selections(qtbot, controller) -> None:
    """This used to clear the *Recent Mods* list, and this test pinned that.

    newtopic63.htm: Clear Selection History deletes "Mod selection information
    for the Contents Panel and Details Panel" — a different list, reached by a
    different command. Both being called history is the whole of the confusion.
    """
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.contents_selection = {"Alpha": "hak/a.hak"}
    save_settings(settings)

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._record_recent_mod("Alpha")
    win._record_recent_mod("Beta")

    win._on_clear_selection_history()

    assert load_settings().contents_selection == {}
    assert win._recent_mods == ["Beta", "Alpha"], "Recent Mods is not this command's"


def test_resetting_the_layout_forgets_the_saved_geometry(qtbot, controller) -> None:
    """Forgetting the geometry alone leaves the splitters where they were
    dragged, which is usually the thing that went wrong."""
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.window_geometry = "c29tZXRoaW5n"
    save_settings(settings)

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._on_reset_window_layout()
    assert load_settings().window_geometry == ""
    assert win._splitters  # and the panes were put back too


def test_view_menu_shows_the_settings_and_rules_files(qtbot, controller, monkeypatch) -> None:
    """VB's View menu opens the two files the app actually runs on.

    Both are real files on disk that a user has no other way to look at from
    inside the app, and both were menu items with no handler until now.
    """
    from vaultkeeper.ui.dialogs.text_viewer import TextViewer

    win = MainWindow(controller)
    qtbot.addWidget(win)

    seen: list = []
    monkeypatch.setattr(
        TextViewer, "show_file", lambda path, title, parent: seen.append((path, title))
    )

    win._on_view_file("MsDisplaySettings")
    win._on_view_file("MsOpenRulesFile")

    assert [title for _p, title in seen] == [
        "Vaultkeeper User Config File",
        "Download Rules File",
    ]
    # The rules path must resolve to a file that exists even on a machine that
    # has never fetched them: the bundled copy is the one in force there.
    assert Path(seen[1][0]).is_file()


def test_view_clipboard_shows_the_clipboard_text(qtbot, controller, monkeypatch) -> None:
    from PySide6.QtWidgets import QApplication

    from vaultkeeper.ui.dialogs.text_viewer import TextViewer

    win = MainWindow(controller)
    qtbot.addWidget(win)

    seen: list = []
    monkeypatch.setattr(
        TextViewer, "show_text", lambda text, title, parent: seen.append(text)
    )

    QApplication.clipboard().setText("Alpha\tSome Mod")
    win._on_view_clipboard()
    QApplication.clipboard().clear()
    win._on_view_clipboard()

    assert seen[0] == "Alpha\tSome Mod"
    assert "no text" in seen[1]


def test_the_mod_list_heading_names_the_profile_and_refreshes(qtbot, controller) -> None:
    """newtopic27: "You can click the Profile name to refresh the Mod List."

    The port showed the profile name nowhere at all, so there was nothing to
    click and nothing telling you which profile was loaded.
    """
    win = MainWindow(controller)
    qtbot.addWidget(win)

    assert win._tree.headerItem().text(0) == controller.store_path.stem
    assert "Click to refresh" in win._tree.header().toolTip()

    refreshed: list[int] = []
    win.refresh = lambda: refreshed.append(1)
    win._tree.header().sectionClicked.emit(0)
    assert refreshed == [1]


def test_the_properties_heading_toggles_the_automatic_height(qtbot, controller) -> None:
    """newtopic33/64: the heading is a second switch for the same Options item,
    so both have to leave the tick and the setting agreeing."""
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.auto_properties_height = False
    save_settings(settings)

    win = MainWindow(controller)
    qtbot.addWidget(win)
    action = win.nit_menu.action("MsPropertiesHeight")

    win._details_list.header().sectionClicked.emit(0)
    assert load_settings().auto_properties_height is True
    assert action.isChecked() is True
    assert "is on." in win.nit_status.mg_info.text()

    win._details_list.header().sectionClicked.emit(0)
    assert load_settings().auto_properties_height is False
    assert action.isChecked() is False


def test_clicking_a_mods_status_icon_offers_to_install_it(qtbot, controller, monkeypatch) -> None:
    """newtopic28: "You can click a Mod's install status icon to Install or
    Uninstall a Mod." Confirmed first — the icon sits next to the target that
    merely selects, and installing by mis-click is not a forgivable mistake."""
    from PySide6.QtWidgets import QMessageBox

    win = MainWindow(controller)
    qtbot.addWidget(win)

    asked: list[str] = []

    def fake_question(parent, title, text, *a, **k):
        asked.append(title)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    installed: list[str] = []
    monkeypatch.setattr(
        controller, "install", lambda names: installed.extend(names) or "installed"
    )

    win._on_state_icon_clicked("Alpha")

    assert asked == ["Install Mod"]
    assert installed == ["Alpha"]


def test_declining_the_status_icon_changes_nothing(qtbot, controller, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    win = MainWindow(controller)
    qtbot.addWidget(win)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    touched: list[str] = []
    monkeypatch.setattr(controller, "install", lambda names: touched.extend(names))
    monkeypatch.setattr(controller, "uninstall", lambda names: touched.extend(names))

    win._on_state_icon_clicked("Alpha")
    assert touched == []


def test_only_the_icon_counts_not_the_label(qtbot, controller) -> None:
    """Qt reports a click on the icon and one on the text as the same item
    click, so the two are told apart by where the pointer was. Picking a mod out
    of the list must not install it."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)

    assert win._tree.select_mod("Alpha")
    item = win._tree.currentItem()
    rect = win._tree.visualItemRect(item)

    assert win._tree.is_over_icon(item, rect.left() + 2), "on the icon"
    assert not win._tree.is_over_icon(item, rect.left() + 200), "on the label"
    assert not win._tree.is_over_icon(item, rect.left() - 10), "left of the row"


def test_character_explorer_select_picks_the_mod(qtbot, controller) -> None:
    """mscharacterviewer.htm: "click the Select button to close the Character
    Explorer and select the mod containing the character file". This screen
    exists to find a character to play; the mod is what you then act on."""
    from types import SimpleNamespace

    from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer

    chosen: list[str] = []
    dlg = CharacterViewer([], on_select=chosen.append)
    qtbot.addWidget(dlg)

    dlg._current_cf = SimpleNamespace(mod_name="Alpha")
    dlg._on_select_mod()

    assert chosen == ["Alpha"]
    assert dlg.result() == dlg.DialogCode.Accepted, "it closes, as the help says"


def test_select_says_so_when_the_character_belongs_to_no_mod(qtbot) -> None:
    from types import SimpleNamespace

    from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer

    chosen: list[str] = []
    dlg = CharacterViewer([], on_select=chosen.append)
    qtbot.addWidget(dlg)

    dlg._current_cf = SimpleNamespace(mod_name="")
    dlg._on_select_mod()

    assert chosen == []
    assert dlg.isVisible() is False or dlg.result() != dlg.DialogCode.Accepted
    assert "no mod" in dlg._select_btn.toolTip()


def test_the_mod_summary_offers_to_record_a_web_page(qtbot, controller, monkeypatch) -> None:
    """recordamodswebpagelink.htm: VB shows an Add Link icon that becomes the
    Download Page icon once set. The port printed the URL as plain text, so the
    one thing anyone wants to do with a URL could not be done with it."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")

    assert "Add link" in win._mod_info.text()

    asked: list[int] = []
    monkeypatch.setattr(win, "_on_edit_web_link", lambda: asked.append(1))
    win._on_mod_info_link("vaultkeeper:add-link")
    assert asked == [1]


def test_a_recorded_page_becomes_a_link(qtbot, controller, monkeypatch) -> None:
    controller.set_mod_web_link("Alpha", "https://neverwintervault.org/project/1")

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")

    assert 'href="https://neverwintervault.org/project/1"' in win._mod_info.text()
    assert "Add link" not in win._mod_info.text()

    opened: list[str] = []
    monkeypatch.setattr(win, "_open_url", opened.append)
    win._on_mod_info_link("https://neverwintervault.org/project/1")
    assert opened == ["https://neverwintervault.org/project/1"]


def test_a_mod_name_with_markup_in_it_is_not_treated_as_markup(qtbot, controller) -> None:
    """The summary is rich text now, so a name containing < or & must not be
    able to rewrite the line it appears on."""
    from vaultkeeper.core.mod_data import ModData

    controller.pd.add_mod(ModData(group="Adv", mod_name="Fire & <b>Ice</b>"))
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Fire & <b>Ice</b>")

    assert "&amp;" in win._mod_info.text()
    assert "&lt;b&gt;" in win._mod_info.text()


def test_new_mod_asks_for_the_group(qtbot, controller, monkeypatch) -> None:
    """addanewmod.htm: "If the Group shown is not the one you want to use for
    the new Mod, select the correct Group from the dropdown list." Only the name
    was asked for, so every new mod landed in the default group."""
    from PySide6.QtWidgets import QInputDialog

    controller.create_group("100.  Community Packs")
    win = MainWindow(controller)
    qtbot.addWidget(win)

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Swordflight", True))
    asked: list[list[str]] = []

    def fake_item(parent, title, label, items, index, editable):
        asked.append(list(items))
        return "100.  Community Packs", True

    monkeypatch.setattr(QInputDialog, "getItem", fake_item)
    win._on_new_mod()

    assert asked and "100.  Community Packs" in asked[0]
    assert controller.pd.mod_item("Swordflight").group == "100.  Community Packs"


def test_new_mod_defaults_to_the_group_in_view(qtbot, controller, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    controller.create_group("100.  Community Packs")
    controller.create_mod("Existing", "100.  Community Packs")
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Existing")

    seen: dict = {}
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New One", True))
    monkeypatch.setattr(
        QInputDialog,
        "getItem",
        lambda parent, title, label, items, index, editable: (
            seen.setdefault("default", items[index]),
            (items[index], True),
        )[1],
    )
    win._on_new_mod()

    assert seen["default"] == "100.  Community Packs"


def test_a_profile_with_no_groups_is_not_asked(qtbot, controller, monkeypatch) -> None:
    """A dropdown with one entry is a dialog that teaches people to click
    through dialogs."""
    from PySide6.QtWidgets import QInputDialog

    win = MainWindow(controller)
    qtbot.addWidget(win)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Solo", True))
    asked: list[int] = []
    monkeypatch.setattr(
        QInputDialog, "getItem", lambda *a, **k: asked.append(1) or ("", True)
    )

    win._on_new_mod()
    assert asked == []
    assert controller.pd.mod_item("Solo") is not None


def test_cancelling_the_group_cancels_the_mod(qtbot, controller, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    controller.create_group("100.  Community Packs")
    win = MainWindow(controller)
    qtbot.addWidget(win)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Nope", True))
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("", False))

    win._on_new_mod()
    assert controller.pd.mod_item("Nope") is None


def test_move_to_group_offers_none_and_means_it(qtbot, controller, monkeypatch) -> None:
    """movingmodsfromonegrouptoanother.htm: "You can also click None from the
    Group drop down list if you want to ungroup the selected Mods." Typing None
    used to make a group actually called None — a different, permanent thing."""
    from PySide6.QtWidgets import QInputDialog

    from vaultkeeper.core import constants as C

    controller.create_group("100.  Community Packs")
    controller.move_to_group(["Alpha"], "100.  Community Packs")

    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")

    offered: list[list[str]] = []

    def fake_item(parent, title, label, items, index, editable):
        offered.append(list(items))
        return "None", True

    monkeypatch.setattr(QInputDialog, "getItem", fake_item)
    win._on_move_to_group()

    assert offered[0][0] == "None"
    assert controller.pd.mod_item("Alpha").group == C.GROUP_NONE
    assert controller.pd.mod_item("Alpha").group != "None"


def test_move_to_group_hides_the_internal_buckets(qtbot, controller, monkeypatch) -> None:
    """The sentinel groups are internal; offering them as a destination invites
    someone to file a mod somewhere the list will not show it."""
    from PySide6.QtWidgets import QInputDialog

    from vaultkeeper.core import constants as C

    win = MainWindow(controller)
    qtbot.addWidget(win)
    _select_mod(win, "Alpha")

    offered: list[list[str]] = []
    monkeypatch.setattr(
        QInputDialog,
        "getItem",
        lambda parent, title, label, items, index, editable: (
            offered.append(list(items)),
            ("", False),
        )[1],
    )
    win._on_move_to_group()

    assert not any(g.startswith(C.GROUP_HIDDEN_PREFIX) for g in offered[0])


def test_reset_taskbar_icon_is_windows_only(qtbot, controller, monkeypatch):
    """Off Windows it says so and never hides the window (VB MsResetTaskbarIcon)."""
    import sys

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.show()
    monkeypatch.setattr(sys, "platform", "darwin")

    win._on_reset_taskbar_icon()

    assert "Windows-only" in win.nit_status.mg_info.text()
    assert win.isVisible()  # not hidden on a non-Windows platform


def test_reset_taskbar_icon_is_a_wired_command(qtbot, controller):
    """No dead menu item: the command dispatches to a handler."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert "MsResetTaskbarIcon" in win.implemented_commands()


def test_debug_options_menu_is_usable_when_shown(qtbot, controller):
    """Regression: the availability pass greyed out Enable Development Folder.

    The toggle is not a dispatch command, so before it joined
    implemented_commands() the availability pass disabled it — and enabling Debug
    Menu Options then opened the submenu onto a dead, greyed item.
    """
    win = MainWindow(controller)
    qtbot.addWidget(win)
    # Enabled independent of the submenu's visibility (the pass disabled it flat).
    assert win.nit_menu.action("DbEnableDevelopmentFolder").isEnabled()
    # And once shown, the submenu itself opens (Qt re-enables its menuAction).
    win.nit_menu.set_debug_menu_visible(True)
    assert win.nit_menu.action("MsDebugOptionsMenu").isEnabled()
