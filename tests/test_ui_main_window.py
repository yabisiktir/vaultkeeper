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
    # A command not wired yet (e.g. Edit Start Screen Prefixes) reports "not available".
    win._on_command("MsEditStartScreenPrefixes")
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


def test_notes_edit_and_persist(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
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
    for dead_id in ("MsCut", "MsAbout", "MsBackupManager"):
        act = win.nit_menu.action(dead_id)
        assert act is not None and not act.isEnabled()
        assert dead_id not in implemented
    for dead_id in ("RbnFontAndColour", "RbnManageWorkshop"):
        button = win.ribbon.button(dead_id)
        assert button is not None and not button.isEnabled()
    for dead_id in ("TsCut", "TsFind"):
        act = win.quick_toolbar.actions_by_id[dead_id]
        assert not act.isEnabled()

    # Implemented items are untouched by the pass (still governed by selection
    # logic or enabled by default).
    assert win.nit_menu.action("MsNewMod").isEnabled()
    assert win.ribbon.button("RbnPlay").isEnabled()
    assert win.quick_toolbar.actions_by_id["TsNewMod"].isEnabled()
    # The handled visibility toggles stay live.
    assert win.nit_menu.action("MsShowRibbon").isEnabled()
    # Unhandled checkable toggles are disabled like any other dead item.
    assert not win.nit_menu.action("MsShowText").isEnabled()


def test_implemented_commands_match_dispatch(qtbot, controller) -> None:
    # Every dispatchable id is reported implemented (single source of truth).
    win = MainWindow(controller)
    qtbot.addWidget(win)
    implemented = win.implemented_commands()
    assert set(win._command_handlers()) <= implemented


def test_basic_settings_opens_behaviour_tab(qtbot, controller, monkeypatch) -> None:
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    win = MainWindow(controller)
    qtbot.addWidget(win)
    seen = {}

    def fake_edit(settings_path=None, parent=None, *, controller=None, start_tab=""):
        seen["start_tab"] = start_tab
        return None  # cancelled

    monkeypatch.setattr(SettingsDialog, "edit", staticmethod(fake_edit))
    win._on_command("MsBasicSettings")
    assert seen["start_tab"] == "Behaviour"
    win._on_command("MsSettings")
    assert seen["start_tab"] == ""


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
