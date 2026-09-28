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

    # Remove the currently selected (B): a saved item is marked, not dropped
    # (VB Cm_Remove), so Undo can bring it back; it is gone from what is saved.
    dlg._web_remove()
    assert [link["text"] for link in dlg.web_links()] == ["A", "C"]
    dlg._menu_undo("web")
    assert [link["text"] for link in dlg.web_links()] == ["B", "A", "C"]


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
    # The item comes from NIT's editor dialog (stood in for here).
    dlg._open_menu_item_editor = lambda *_a: ("New Link", "https://new.example")

    dlg.web_tree.setCurrentItem(dlg.web_tree.topLevelItem(0))
    dlg._web_add()
    names = [dlg.web_tree.topLevelItem(i).text(0) for i in range(4)]
    assert names == ["A", "New Link", "B", "C"]
    assert dlg.web_tree.currentItem().text(1) == "https://new.example"

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
    dlg._open_menu_item_editor = lambda *_a: ("New Program", "/new")

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
        # NIT's keys (Insert, Ctrl+E, Delete), all *widget* shortcuts so they
        # never take a key from another field (the Rename regression).
        shortcuts = tree.findChildren(QShortcut)
        assert [s.key().toString() for s in shortcuts] == [
            "Ins", "Ctrl+Ins", "Ctrl+E", "Ctrl+Z", "Del",
        ]
        assert all(s.context() == Qt.ShortcutContext.WidgetShortcut for s in shortcuts)

    assert offered[0] == offered[1] == [
        "New Menu Item", "Insert Separator", "Edit Menu Item", "Undo", "",
        "Move Up", "Move Down", "Move To", "", "Remove",
    ]


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


def test_changed_preferences_are_shown_in_italics(qtbot):
    """bhpreferences.htm: "Preferences you change … are displayed in italics."

    Nine tabs of check boxes; without this, knowing what you are about to save
    means re-reading every page.
    """
    settings = Settings()
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)

    assert dlg.changed_widgets() == []

    box = dlg.recycle
    was = box.isChecked()
    box.setChecked(not was)
    assert dlg.changed_widgets() == [box]
    assert box.font().italic()

    # Putting it back clears the mark rather than leaving a false one.
    box.setChecked(was)
    assert dlg.changed_widgets() == []
    assert not box.font().italic()


def test_changed_marks_cover_text_and_number_fields(qtbot):
    settings = Settings()
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)

    from PySide6.QtWidgets import QSpinBox

    spin = dlg.findChild(QSpinBox)
    assert spin is not None
    spin.setValue(spin.value() + 1)
    assert spin in dlg.changed_widgets()


def test_workshop_management_preference_round_trips(qtbot):
    """newtopic19.htm: enabling management + a manual content folder."""
    settings = Settings(manage_steam_workshop=False)
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)

    assert dlg.manage_steam_workshop.isChecked() is False
    dlg.manage_steam_workshop.setChecked(True)
    dlg.apply_to(settings)
    assert settings.manage_steam_workshop is True


def test_use_move_preference_round_trips(qtbot):
    settings = Settings(use_move_on_add=True)
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg.use_move_on_add.isChecked() is True
    dlg.use_move_on_add.setChecked(False)
    dlg.apply_to(settings)
    assert settings.use_move_on_add is False


def test_the_two_thresholds_are_editable(qtbot) -> None:
    # VB ConfigSavesThreshold / ConfigWizardFileThreshold were honoured but not editable.
    settings = Settings(saves_threshold=700, wizard_file_threshold=15000)
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg.saves_threshold.value() == 700
    dlg.saves_threshold.setValue(250)
    dlg.wizard_file_threshold.setValue(40000)

    out = Settings()
    dlg.apply_to(out)

    assert out.saves_threshold == 250
    assert out.wizard_file_threshold == 40000


def test_edit_changes_the_selected_item_through_the_editor(qtbot):
    """VB ChangeMenuItem: the editor gets the item and every *other* item's text."""
    settings = Settings(web_links=[{"text": "A", "url": "a"}, {"text": "B", "url": "b"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    seen = []

    def editor(kind, text, location, others):
        seen.append((kind, text, location, others))
        return ("A2", "https://a2.example")

    dlg._open_menu_item_editor = editor
    dlg.web_tree.setCurrentItem(dlg.web_tree.topLevelItem(0))
    dlg._menu_edit("web")

    assert seen == [("web", "A", "a", ["B"])]
    assert dlg.web_links()[0] == {"text": "A2", "url": "https://a2.example"}


def test_separators_round_trip_and_reach_the_menus(qtbot):
    """VB Insert Separator (Ctrl+Insert): a <Separator> row, saved and shown as one."""
    from PySide6.QtWidgets import QMenu

    from vaultkeeper.config.settings import MENU_SEPARATOR
    from vaultkeeper.ui.menu_bar import NitMenuBar

    settings = Settings(web_links=[{"text": "A", "url": "https://a"}, {"text": "B", "url": "https://b"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg.web_tree.setCurrentItem(dlg.web_tree.topLevelItem(0))
    dlg._menu_insert_separator("web")
    assert dlg.web_tree.topLevelItem(1).text(0) == "<Separator>"
    assert dlg.web_links()[1] == MENU_SEPARATOR

    dlg.apply_to(settings)
    again = SettingsDialog(settings)
    qtbot.addWidget(again)
    assert again.web_tree.topLevelItem(1).text(0) == "<Separator>"

    bar = NitMenuBar()
    qtbot.addWidget(bar)
    bar.populate_web_menu(settings.web_links, lambda _u: None)
    menu: QMenu = bar.menus["MsWeb"]
    assert [a.isSeparator() for a in menu.actions()] == [False, True, False]

    # A separator has nothing to edit and goes at once on Remove.
    again.web_tree.setCurrentItem(again.web_tree.topLevelItem(1))
    again._menu_remove("web")
    assert all("separator" not in link for link in again.web_links())


def test_move_to_puts_the_item_where_you_click(qtbot):
    """VB Cm_MoveTo / MoveItems: up the list before the target, down it after."""
    settings = Settings(web_links=[{"text": t, "url": t} for t in "ABCD"])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    tree = dlg.web_tree

    def names():
        return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]

    tree.setCurrentItem(tree.topLevelItem(0))
    dlg._menu_move_to("web")
    dlg._menu_move_to_target("web", tree.topLevelItem(2))  # A down onto C
    assert names() == ["B", "C", "A", "D"]
    assert not dlg._move_to_buttons["web"].isChecked()

    tree.setCurrentItem(tree.topLevelItem(3))
    dlg._menu_move_to("web")
    dlg._menu_move_to_target("web", tree.topLevelItem(0))  # D up onto B
    assert names() == ["D", "B", "C", "A"]

    # Clicking a row with no Move To in progress moves nothing.
    dlg._menu_move_to_target("web", tree.topLevelItem(2))
    assert names() == ["D", "B", "C", "A"]


def test_undo_restores_an_edited_item(qtbot):
    settings = Settings(run_links=[{"text": "Leto", "path": "/leto"}])
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    dlg._open_menu_item_editor = lambda *_a: ("Leto II", "/leto2")
    dlg.run_tree.setCurrentItem(dlg.run_tree.topLevelItem(0))
    dlg._menu_edit("run")
    assert dlg.run_links() == [{"text": "Leto II", "path": "/leto2"}]

    dlg._menu_undo("run")
    assert dlg.run_links() == [{"text": "Leto", "path": "/leto"}]
