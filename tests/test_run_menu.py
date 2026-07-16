"""Run Menu — user-defined external launch programs (VB Settings.RunMenu / SetRunMenu).

The port already ports the fixed Play / Toolset entries; this adds the user-defined
programs the VB Run menu supports (the analogue of the Web menu's custom links).
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from vaultkeeper.config.settings import Settings, load_settings, save_settings


# -- settings model -------------------------------------------------------- #
def test_run_links_default_empty():
    assert Settings().run_links == []


def test_run_links_round_trip(tmp_path):
    path = tmp_path / "s.json"
    save_settings(
        Settings(run_links=[{"text": "Leto", "path": "/opt/leto/leto"}]), path
    )
    assert load_settings(path).run_links == [{"text": "Leto", "path": "/opt/leto/leto"}]


# -- populate_run_menu (VB SetRunMenu) ------------------------------------- #
def _menu_bar(qtbot):
    from vaultkeeper.ui.menu_bar import NitMenuBar

    bar = NitMenuBar()
    qtbot.addWidget(bar)
    return bar


def test_run_menu_fixed_items_only_when_empty(qtbot):
    bar = _menu_bar(qtbot)
    bar.populate_run_menu([], lambda _p: None)
    menu = bar.menus["MsRun"]
    # Just the two fixed items (Play / Toolset), no trailing separator.
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == ["&Neverwinter Nights", "Neverwinter Nights &Toolset"]
    assert not any(a.isSeparator() for a in menu.actions())


def test_run_menu_appends_user_items_after_separator(qtbot):
    bar = _menu_bar(qtbot)
    bar.populate_run_menu(
        [{"text": "Leto", "path": "/x/leto"}, {"text": "Editor", "path": "/x/ed"}],
        lambda _p: None,
    )
    menu = bar.menus["MsRun"]
    acts = menu.actions()
    # Play, Toolset, separator, Leto, Editor.
    assert acts[0].text() == "&Neverwinter Nights"
    assert acts[1].text() == "Neverwinter Nights &Toolset"
    assert acts[2].isSeparator()
    assert [a.text() for a in acts[3:]] == ["Leto", "Editor"]
    assert acts[3].toolTip() == "/x/leto"


def test_run_menu_repopulate_replaces_user_items(qtbot):
    bar = _menu_bar(qtbot)
    bar.populate_run_menu([{"text": "Old", "path": "/x/old"}], lambda _p: None)
    bar.populate_run_menu([{"text": "New", "path": "/x/new"}], lambda _p: None)
    menu = bar.menus["MsRun"]
    user = [a.text() for a in menu.actions() if not a.isSeparator()][2:]
    assert user == ["New"]  # Old was removed, not accumulated


def test_run_menu_item_triggers_launch_with_path(qtbot):
    bar = _menu_bar(qtbot)
    launched: list[str] = []
    bar.populate_run_menu(
        [{"text": "Leto", "path": "/x/leto"}], lambda p: launched.append(p)
    )
    menu = bar.menus["MsRun"]
    leto = next(a for a in menu.actions() if a.text() == "Leto")
    leto.trigger()
    assert launched == ["/x/leto"]


def test_run_menu_drops_blank_entries(qtbot):
    bar = _menu_bar(qtbot)
    bar.populate_run_menu([{"text": "", "path": ""}], lambda _p: None)
    menu = bar.menus["MsRun"]
    assert not any(a.isSeparator() for a in menu.actions())


# -- _on_run_program (VB RunMenu_Click Case Else -> RunProgram) ------------ #
def _window(tmp_path, qtbot):
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    ctrl = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    win = MainWindow(controller=ctrl)
    qtbot.addWidget(win)
    return win


def test_on_run_program_launches_existing(tmp_path, qtbot, monkeypatch):
    win = _window(tmp_path, qtbot)
    prog = tmp_path / "tool.sh"
    prog.write_text("#!/bin/sh\n")

    calls = {}
    from PySide6.QtCore import QProcess

    def fake_start_detached(program, args, workdir):
        calls["program"], calls["args"], calls["workdir"] = program, args, workdir
        return True

    monkeypatch.setattr(QProcess, "startDetached", staticmethod(fake_start_detached))
    win._on_run_program(str(prog))
    assert calls["program"] == str(prog)
    assert calls["workdir"] == str(tmp_path)


def test_on_run_program_missing_warns(tmp_path, qtbot, monkeypatch):
    win = _window(tmp_path, qtbot)
    warned = {"n": 0}
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: warned.__setitem__("n", warned["n"] + 1)
    )
    # A path that does not exist must not attempt to launch, just warn.
    win._on_run_program(str(tmp_path / "nope.exe"))
    assert warned["n"] == 1


# -- Settings dialog Run Menu tab ------------------------------------------ #
def test_settings_dialog_run_menu_round_trip(qtbot):
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    settings = Settings(run_links=[{"text": "Leto", "path": "/x/leto"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    # Existing entry is shown.
    assert dlg.run_tree.topLevelItemCount() == 1
    # Add another row and write back.
    dlg._add_run_row("Editor", "/x/ed")
    dlg.apply_to(settings)
    assert settings.run_links == [
        {"text": "Leto", "path": "/x/leto"},
        {"text": "Editor", "path": "/x/ed"},
    ]


def test_run_menu_tab_present(qtbot):
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    dlg = SettingsDialog(Settings())
    qtbot.addWidget(dlg)
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert "Run Menu" in titles


def test_settings_dialog_run_menu_reset(qtbot):
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    settings = Settings(run_links=[{"text": "Leto", "path": "/x/leto"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg._run_reset()  # restores defaults (empty)
    dlg.apply_to(settings)
    assert settings.run_links == []
