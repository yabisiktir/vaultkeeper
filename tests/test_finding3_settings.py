"""Finding-3 remaining settings: delete_leto_logs, confirm_saves, portrait_display_size.

These are the last three of the ten "safe MISSING" settings from
``docs/parity_audit/FINDING_3_SETTINGS.md`` — each wired to real behaviour ported
from the VB source (``ConfigDeleteLetoLogs`` / ``BehaviourConfirmSaves`` /
``ConfigPortraitDisplaySize``).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.core import constants as C
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, **settings_kw) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    settings_path = tmp_path / "settings.json"
    save_settings(Settings(**settings_kw), settings_path)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        settings_path=settings_path,
    )


# -- defaults (match VB App.config) ---------------------------------------- #
def test_new_settings_defaults():
    s = Settings()
    assert s.delete_leto_logs is True
    assert s.confirm_saves is True
    assert s.portrait_display_size == "Huge"


def test_settings_round_trip(tmp_path):
    path = tmp_path / "s.json"
    save_settings(
        Settings(
            delete_leto_logs=False, confirm_saves=False, portrait_display_size="Medium"
        ),
        path,
    )
    s = load_settings(path)
    assert s.delete_leto_logs is False
    assert s.confirm_saves is False
    assert s.portrait_display_size == "Medium"


# -- delete_leto_logs: the global sweep ------------------------------------ #
def test_remove_all_leto_log_files_sweeps_installer_and_game_folders(tmp_path):
    # Create the mod (with a Leto log in its installer) BEFORE opening the profile
    # so the scan registers it, mirroring test_cleanup_files.
    installer = tmp_path / "Profiles" / "P" / "My Mod" / C.MOD_INSTALLER_DIR
    (installer / "hak").mkdir(parents=True)
    (installer / "hak" / "content.hak").write_bytes(b"HAK")
    (installer / "override").mkdir()
    (installer / "override" / C.LETO_LOG_FILENAME).write_bytes(b"log")
    ctrl = _controller(tmp_path)
    ctrl.create_installer("My Mod")  # registers the payload files

    # Drop a loose Leto log into one of the resolved game folders too.
    game_folder = next(iter(ctrl.ctx.game_folders.values()))
    game_folder.mkdir(parents=True, exist_ok=True)
    (game_folder / C.LETO_LOG_FILENAME).write_bytes(b"log")

    removed = ctrl.remove_all_leto_log_files(to_trash=False)
    assert removed == 2
    assert not (installer / "override" / C.LETO_LOG_FILENAME).exists()
    assert not (game_folder / C.LETO_LOG_FILENAME).exists()
    # The hak payload is untouched.
    assert (installer / "hak" / "content.hak").exists()
    md = ctrl.pd.mod_item("My Mod")
    assert not any(fk.filename == C.LETO_LOG_FILENAME for fk in md.files)


def test_remove_all_leto_log_files_noop_when_clean(tmp_path):
    ctrl = _controller(tmp_path)
    assert ctrl.remove_all_leto_log_files(to_trash=False) == 0


# -- delete_leto_logs: the manual command's visibility (VB Not ConfigDeleteLetoLogs) #
def test_leto_menu_hidden_when_auto_delete_on(tmp_path, qtbot):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller=_controller(tmp_path, delete_leto_logs=True))
    qtbot.addWidget(win)
    assert win.nit_menu.actions_by_id["MsRemoveLetoLogFiles"].isVisible() is False


def test_leto_menu_shown_when_auto_delete_off(tmp_path, qtbot):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller=_controller(tmp_path, delete_leto_logs=False))
    qtbot.addWidget(win)
    assert win.nit_menu.actions_by_id["MsRemoveLetoLogFiles"].isVisible() is True


# -- confirm_saves: the Mod Notes save prompt ------------------------------ #
def _win_with_notes(tmp_path, qtbot, **settings_kw):
    from vaultkeeper.ui.main_window import MainWindow

    ctrl = _controller(tmp_path, **settings_kw)
    for name in ("Alpha", "Beta"):
        ctrl.pd.add_mod(
            ModData(group=C.GROUP_NONE, mod_name=name, mod_state=State.NOT_INSTALLED)
        )
    ctrl.save()
    win = MainWindow(controller=ctrl)
    qtbot.addWidget(win)
    return ctrl, win


def test_confirm_saves_off_saves_silently(tmp_path, qtbot, monkeypatch):
    ctrl, win = _win_with_notes(tmp_path, qtbot, confirm_saves=False)
    # No dialog must be shown when confirm-saves is off.
    called = {"q": 0}
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: called.__setitem__("q", called["q"] + 1)
        or QMessageBox.StandardButton.Yes,
    )
    win._notes_mod = "Alpha"
    win._details.setPlainText("silent note")
    win._details.document().setModified(True)
    win._save_current_notes()
    assert called["q"] == 0
    assert ctrl.read_notes("Alpha") == "silent note"


def test_confirm_saves_on_yes_saves(tmp_path, qtbot, monkeypatch):
    ctrl, win = _win_with_notes(tmp_path, qtbot, confirm_saves=True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    win._notes_mod = "Alpha"
    win._details.setPlainText("kept note")
    win._details.document().setModified(True)
    win._save_current_notes()
    assert ctrl.read_notes("Alpha") == "kept note"


def test_confirm_saves_on_no_discards(tmp_path, qtbot, monkeypatch):
    ctrl, win = _win_with_notes(tmp_path, qtbot, confirm_saves=True)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    win._notes_mod = "Alpha"
    win._details.setPlainText("dropped note")
    win._details.document().setModified(True)
    win._save_current_notes()
    # Declining discards the edit — nothing persisted.
    assert ctrl.read_notes("Alpha") == ""


# -- portrait_display_size: the Character Explorer preview ------------------ #
def test_portrait_box_mapping():
    from vaultkeeper.ui.dialogs.character_viewer import PORTRAIT_SIZES, portrait_box

    assert portrait_box("Huge") == PORTRAIT_SIZES["Huge"] == 256
    assert portrait_box("Large") == 128
    assert portrait_box("Medium") == 64
    # An unknown value falls back to the default (Huge).
    assert portrait_box("nonsense") == 256


def test_character_viewer_uses_setting_size(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer

    dlg = CharacterViewer([], None, portrait_size="Medium")
    qtbot.addWidget(dlg)
    assert dlg._portrait_box == 64
    assert dlg._portrait.height() == 64


# -- the Settings dialog surfaces + round-trips all three ------------------- #
def test_settings_dialog_round_trips_new_fields(qtbot):
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    settings = Settings()
    dlg = SettingsDialog(settings)
    qtbot.addWidget(dlg)
    # The widgets reflect the current values.
    assert dlg.delete_leto_logs.isChecked() is True
    assert dlg.confirm_saves.isChecked() is True
    assert dlg.portrait_display_size.currentText() == "Huge"
    # Flip each and write back.
    dlg.delete_leto_logs.setChecked(False)
    dlg.confirm_saves.setChecked(False)
    dlg.portrait_display_size.setCurrentText("Large")
    dlg.apply_to(settings)
    assert settings.delete_leto_logs is False
    assert settings.confirm_saves is False
    assert settings.portrait_display_size == "Large"
