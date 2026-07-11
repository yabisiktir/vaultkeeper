"""Tests for the mod-list right-click context menu (VB CmMods)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def _window(qtbot, tmp_path: Path) -> MainWindow:
    pd = ProfileData()
    pd.add_mod(ModData(group="G", mod_name="A"))
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )
    win = MainWindow(controller=controller)
    qtbot.addWidget(win)
    return win


def test_context_menu_items_match_vb_order(qtbot, tmp_path: Path) -> None:
    win = _window(qtbot, tmp_path)
    menu = win._build_mods_context_menu()

    # Non-separator actions, in order, reuse the same menu-bar QActions (CmMods).
    expected = [i for i in win._MODS_CONTEXT_ITEMS if i is not None]
    got_actions = [a for a in menu.actions() if not a.isSeparator()]
    assert [a.text() for a in got_actions] == [
        win.nit_menu.action(i).text() for i in expected
    ]
    # Same QAction objects -> triggering routes through the existing wiring.
    for action, ident in zip(got_actions, expected, strict=True):
        assert action is win.nit_menu.action(ident)


def test_context_menu_has_separators(qtbot, tmp_path: Path) -> None:
    win = _window(qtbot, tmp_path)
    menu = win._build_mods_context_menu()
    assert any(a.isSeparator() for a in menu.actions())
    # Never starts or ends with a separator.
    actions = menu.actions()
    assert not actions[0].isSeparator()
    assert not actions[-1].isSeparator()


def test_context_menu_reflects_selection_enable_state(qtbot, tmp_path: Path) -> None:
    win = _window(qtbot, tmp_path)
    # With nothing selected, Install is disabled; it shares the menu-bar action.
    win._on_selection_changed([])
    menu = win._build_mods_context_menu()
    install = next(a for a in menu.actions() if a is win.nit_menu.action("MsInstall"))
    assert install.isEnabled() is False
