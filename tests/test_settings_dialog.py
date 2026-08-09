"""Tests for the Settings dialog."""

from __future__ import annotations

from vaultkeeper.config.settings import Settings
from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog


def test_dialog_reflects_settings(qtbot):
    settings = Settings(
        recycle_on_delete=False,
        validate_game_config_on_startup=True,
        nwn_path="/games/NWN",
        active_profile="My Mods",
    )
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert not dlg.recycle.isChecked()
    assert dlg.startup_check.isChecked()


def test_reset_all_restores_preference_defaults(qtbot):
    # VB CmsResetAll: "Restore All Settings to Default Values".
    settings = Settings(
        recycle_on_delete=False,
        convert_bik_files=True,
        default_group="Adventures",
        startup_sound=True,
        theme="dark",
        nwn_path="/games/NWN",
        active_profile="My Mods",
    )
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg._on_reset_all()

    # Preferences are back at their dataclass defaults …
    defaults = Settings()
    assert dlg.recycle.isChecked() == defaults.recycle_on_delete
    assert dlg.convert_bik.isChecked() == defaults.convert_bik_files
    assert dlg.default_group.text() == defaults.default_group
    assert dlg.startup_sound.isChecked() == defaults.startup_sound
    # … and applying persists those defaults while identity settings are kept.
    out = Settings(nwn_path="/games/NWN", active_profile="My Mods")
    dlg.apply_to(out)
    assert out.recycle_on_delete == defaults.recycle_on_delete
    assert out.convert_bik_files == defaults.convert_bik_files
    assert out.nwn_path == "/games/NWN"  # preserved, not defaulted


def test_reset_preserves_identity_labels(qtbot):
    # The General tab's read-only path/profile labels survive a reset.
    settings = Settings(nwn_path="/games/NWN", active_profile="My Mods", recycle_on_delete=False)
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg._on_reset_all()
    # The path is shown via a QLabel; check the General page still references it.
    from PySide6.QtWidgets import QLabel

    texts = [w.text() for w in dlg.tabs.widget(0).findChildren(QLabel)]
    assert "/games/NWN" in texts
    assert "My Mods" in texts


def test_reset_panel_only_resets_current_tab(qtbot):
    # VB CmsResetPanel: restore just the current page.
    settings = Settings(recycle_on_delete=False, convert_bik_files=True)
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    # Edit the Behaviour tab, then reset only General.
    dlg.convert_bik.setChecked(True)
    for i in range(dlg.tabs.count()):
        if dlg.tabs.tabText(i) == "General":
            dlg.tabs.setCurrentIndex(i)
    dlg._on_reset_panel()
    assert dlg.recycle.isChecked() is True  # General reset to default
    assert dlg.convert_bik.isChecked() is True  # Behaviour left untouched


def test_reset_panel_label_tracks_current_tab(qtbot):
    dlg = SettingsDialog(Settings())
    qtbot.addWidget(dlg)
    for i in range(dlg.tabs.count()):
        if dlg.tabs.tabText(i) == "Appearance":
            dlg.tabs.setCurrentIndex(i)
    dlg._update_reset_menu()
    assert dlg._reset_panel_action.text() == "Restore Appearance"
    assert dlg._reset_panel_action.isEnabled()


def test_apply_to_writes_back(qtbot):
    settings = Settings(recycle_on_delete=True, validate_game_config_on_startup=True)
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg.recycle.setChecked(False)
    dlg.startup_check.setChecked(False)
    dlg.apply_to(settings)
    assert settings.recycle_on_delete is False
    assert settings.validate_game_config_on_startup is False


def test_viewer_tab_round_trips(qtbot):
    settings = Settings(inventory_nwn_style=True, hak_item_icons=False)
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    # The dedicated Character / Save Viewer tab exists and reflects the settings.
    assert any(
        dlg.tabs.tabText(i) == "Character / Save Viewer" for i in range(dlg.tabs.count())
    )
    assert dlg.inventory_nwn_style.isChecked() is True
    assert dlg.hak_item_icons.isChecked() is False
    dlg.inventory_nwn_style.setChecked(False)
    dlg.hak_item_icons.setChecked(True)
    dlg.apply_to(settings)
    assert settings.inventory_nwn_style is False
    assert settings.hak_item_icons is True


def test_edit_persists_on_accept(qtbot, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    from vaultkeeper.config.settings import save_settings

    save_settings(Settings(recycle_on_delete=True), settings_path)

    # Simulate the user unchecking recycle and pressing OK.
    def fake_exec(self):
        self.recycle.setChecked(False)
        return SettingsDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    result = SettingsDialog.edit(settings_path)
    assert result is not None
    assert result.recycle_on_delete is False

    from vaultkeeper.config.settings import load_settings

    assert load_settings(settings_path).recycle_on_delete is False


def test_edit_cancel_returns_none(qtbot, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(
        SettingsDialog, "exec", lambda self: SettingsDialog.DialogCode.Rejected
    )
    assert SettingsDialog.edit(settings_path) is None


# -- Web Menu editor -------------------------------------------------------- #


def test_web_menu_reflects_and_edits(qtbot):
    settings = Settings(web_links=[{"text": "Vault", "url": "https://v.example"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg.web_tree.topLevelItemCount() == 1
    assert dlg.web_tree.topLevelItem(0).text(0) == "Vault"

    # Add a link and write back.
    dlg._add_web_row("Nexus", "https://n.example")
    dlg.apply_to(settings)
    assert settings.web_links == [
        {"text": "Vault", "url": "https://v.example"},
        {"text": "Nexus", "url": "https://n.example"},
    ]


def test_web_menu_remove_and_move(qtbot):
    settings = Settings(
        web_links=[
            {"text": "A", "url": "a"},
            {"text": "B", "url": "b"},
            {"text": "C", "url": "c"},
        ]
    )
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)

    # Move B up (select index 1, move -1).
    dlg.web_tree.setCurrentItem(dlg.web_tree.topLevelItem(1))
    dlg._web_move(-1)
    assert [dlg.web_tree.topLevelItem(i).text(0) for i in range(3)] == ["B", "A", "C"]

    # Remove the currently selected (B).
    dlg._web_remove()
    assert [dlg.web_tree.topLevelItem(i).text(0) for i in range(2)] == ["A", "C"]


def test_new_menu_item_lands_after_the_selected_one(qtbot):
    """bhwebmenu/bhrunmenu: "Select the item that will precede your new entry."

    It used to append to the end, so placing an entry in a long menu meant
    clicking Move Up until it got there.
    """
    settings = Settings(
        web_links=[
            {"text": "A", "url": "a"},
            {"text": "B", "url": "b"},
            {"text": "C", "url": "c"},
        ]
    )
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)

    dlg.web_tree.setCurrentItem(dlg.web_tree.topLevelItem(0))
    dlg._web_add()
    names = [dlg.web_tree.topLevelItem(i).text(0) for i in range(4)]
    assert names == ["A", "New Link", "B", "C"]
    # And the new row is what you are now editing.
    assert dlg.web_tree.currentItem().text(0) == "New Link"

    # Nothing selected: it goes on the end, which is the only place left.
    dlg.web_tree.setCurrentItem(None)
    dlg._web_add()
    assert dlg.web_tree.topLevelItem(4).text(0) == "New Link"


def test_run_menu_new_item_also_inserts_after(qtbot):
    settings = Settings(
        run_links=[{"text": "One", "path": "/one"}, {"text": "Two", "path": "/two"}]
    )
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)

    dlg.run_tree.setCurrentItem(dlg.run_tree.topLevelItem(0))
    dlg._run_add()
    assert [dlg.run_tree.topLevelItem(i).text(0) for i in range(3)] == [
        "One",
        "New Program",
        "Two",
    ]


def test_menu_editors_answer_a_right_click(qtbot):
    """"Right-Click… to access the actions menu" — it did nothing before."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QShortcut
    from PySide6.QtWidgets import QMenu

    settings = Settings(web_links=[{"text": "A", "url": "a"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)

    offered = []
    for tree in (dlg.web_tree, dlg.run_tree):
        assert tree.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
        menu = tree.findChild(QMenu)
        assert menu is not None
        offered.append([a.text() for a in menu.actions()])
        # Shown with popup(), so emitting the request does not block a test.
        tree.customContextMenuRequested.emit(QPoint(4, 4))
        assert menu.isVisible()
        menu.hide()
        # Insert is a *widget* shortcut, so the inline editor keeps its own keys
        # (the Rename regression in ui/file_view.py).
        shortcuts = tree.findChildren(QShortcut)
        assert [s.key().toString() for s in shortcuts] == ["Ins"]
        assert all(s.context() == Qt.ShortcutContext.WidgetShortcut for s in shortcuts)

    assert offered[0][0] == "New Menu Item"
    assert "Browse…" in offered[1]


def test_web_menu_keeps_an_ampersand_as_an_alt_key(qtbot):
    """"&Search the Vault … launched using the Alt, W, S key sequence."

    Qt reads the ampersand itself, so this only needs the text to reach the
    action unmangled — which is worth pinning, because escaping it anywhere
    along the way would silently cost the feature.
    """
    from vaultkeeper.ui.menu_bar import NitMenuBar

    bar = NitMenuBar()
    qtbot.addWidget(bar)
    bar.populate_web_menu([{"text": "&Search the Vault", "url": "https://x"}], print)

    assert bar.menus["MsWeb"].actions()[0].text() == "&Search the Vault"


def test_web_menu_reset_to_defaults(qtbot):
    from vaultkeeper.config.settings import default_web_links

    settings = Settings(web_links=[{"text": "Custom", "url": "x"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg._web_reset()
    dlg.apply_to(settings)
    assert settings.web_links == default_web_links()


def test_web_menu_drops_blank_rows(qtbot):
    settings = Settings(web_links=[])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg._add_web_row("", "")  # fully blank → dropped
    dlg._add_web_row("Real", "https://r")
    assert dlg.web_links() == [{"text": "Real", "url": "https://r"}]


# -- Behaviour preferences (VB Settings Behaviour group) ------------------- #


def test_behaviour_tab_reflects_and_applies(qtbot):
    settings = Settings(
        convert_bik_files=True,
        install_after_create=True,
        remember_window_position=False,
        startup_sound=True,
    )
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg.convert_bik.isChecked()
    assert dlg.install_after_create.isChecked()
    assert not dlg.remember_window.isChecked()
    assert dlg.startup_sound.isChecked()

    dlg.convert_bik.setChecked(False)
    dlg.install_after_create.setChecked(False)
    dlg.remember_window.setChecked(True)
    dlg.apply_to(settings)
    assert settings.convert_bik_files is False
    assert settings.install_after_create is False
    assert settings.remember_window_position is True


def test_behaviour_prefs_round_trip_through_store(tmp_path):
    from vaultkeeper.config.settings import load_settings, save_settings

    path = tmp_path / "settings.json"
    save_settings(Settings(convert_bik_files=True, install_after_create=True), path)
    loaded = load_settings(path)
    assert loaded.convert_bik_files is True
    assert loaded.install_after_create is True


def test_exact_item_icons_round_trips(qtbot, tmp_path):
    """The choice between each item's own picture and one default per type."""
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    settings = Settings()
    assert settings.exact_item_icons is True  # match the game by default
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg.exact_item_icons.isChecked()
    dlg.exact_item_icons.setChecked(False)
    dlg.apply_to(settings)
    assert settings.exact_item_icons is False


# -- Downloads tab ------------------------------------------------------------- #
def test_the_downloads_tab_reflects_the_chosen_method(qtbot):
    dlg = SettingsDialog(Settings(vault_download_method="scrape", vault_rules_online=False))
    qtbot.addWidget(dlg)
    assert dlg.vault_download_method.currentText().startswith("Read the project")
    assert not dlg.vault_rules_online.isChecked()


def test_the_api_is_the_default_method(qtbot):
    dlg = SettingsDialog(Settings())
    qtbot.addWidget(dlg)
    assert dlg.vault_download_method.currentText().startswith("The Vault's API")
    assert dlg.vault_rules_online.isChecked()


def test_an_unknown_stored_method_falls_back_to_the_api(qtbot):
    """A hand-edited settings file must not leave the combo showing something else."""
    dlg = SettingsDialog(Settings(vault_download_method="carrier pigeon"))
    qtbot.addWidget(dlg)
    settings = Settings()
    dlg.apply_to(settings)
    assert settings.vault_download_method == "api"


def test_choosing_page_scraping_is_written_back(qtbot):
    settings = Settings()
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg.vault_download_method.setCurrentIndex(1)
    dlg.vault_rules_online.setChecked(False)
    dlg.apply_to(settings)
    assert settings.vault_download_method == "scrape"
    assert settings.vault_rules_online is False
