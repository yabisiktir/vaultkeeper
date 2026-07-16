"""Alias Section editor — view/edit nwn.ini [Alias] behind a config-isolation confirm."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game.nwn_folders import read_alias_section, write_alias_section
from vaultkeeper.ui.controller import ProfileController

_NWN_INI = """\
[Display Options]
Width=1920

[Alias]
HAK=./hak
TLK=./tlk
OVERRIDE=/custom/override
SAVES=./saves

[Sound Options]
Volume=100
"""


def _write_ini(user_dir: Path, text: str = _NWN_INI) -> Path:
    user_dir.mkdir(parents=True, exist_ok=True)
    ini = user_dir / "nwn.ini"
    ini.write_text(text, encoding="utf-8")
    return ini


# -- headless read/write --------------------------------------------------- #
def test_read_alias_section_preserves_keys_and_order(tmp_path):
    _write_ini(tmp_path)
    rows = read_alias_section(tmp_path)
    assert rows == [
        ("HAK", "./hak"),
        ("TLK", "./tlk"),
        ("OVERRIDE", "/custom/override"),
        ("SAVES", "./saves"),
    ]


def test_read_alias_section_missing_ini():
    assert read_alias_section(Path("/no/such/dir")) == []


def test_write_alias_section_updates_only_target_and_backs_up(tmp_path):
    ini = _write_ini(tmp_path)
    changed = write_alias_section(tmp_path, {"HAK": "/new/hak", "TLK": "./tlk"})
    # HAK changed; TLK unchanged (same value) so not counted.
    assert changed == 1
    text = ini.read_text()
    assert "HAK=/new/hak" in text
    assert "TLK=./tlk" in text
    # Everything else is byte-for-byte intact.
    assert "[Display Options]" in text and "Width=1920" in text
    assert "[Sound Options]" in text and "Volume=100" in text
    assert "OVERRIDE=/custom/override" in text
    # A backup of the original was created.
    bak = tmp_path / "nwn.ini.bak"
    assert bak.exists()
    assert "HAK=./hak" in bak.read_text()  # the pristine original


def test_write_alias_section_no_change_no_write(tmp_path):
    ini = _write_ini(tmp_path)
    before = ini.stat().st_mtime_ns
    assert write_alias_section(tmp_path, {"HAK": "./hak"}) == 0  # same value
    assert not (tmp_path / "nwn.ini.bak").exists()
    assert ini.stat().st_mtime_ns == before  # untouched


def test_write_alias_section_ignores_unknown_keys(tmp_path):
    _write_ini(tmp_path)
    assert write_alias_section(tmp_path, {"NOTAKEY": "/x"}) == 0


def test_write_alias_section_missing_ini_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        write_alias_section(tmp_path, {"HAK": "/x"})


# -- controller ------------------------------------------------------------ #
def _controller(tmp_path: Path, *, with_ini: bool = True) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    user_dir = tmp_path / "user"
    if with_ini:
        _write_ini(user_dir)
    else:
        user_dir.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=user_dir,
    )


def test_alias_report_lists_rows(tmp_path):
    ctrl = _controller(tmp_path)
    report = ctrl.alias_locations_report()
    assert report["exists"] is True
    keys = [r["key"] for r in report["rows"]]
    assert keys == ["HAK", "TLK", "OVERRIDE", "SAVES"]


def test_alias_report_no_ini(tmp_path):
    ctrl = _controller(tmp_path, with_ini=False)
    report = ctrl.alias_locations_report()
    assert report["exists"] is False
    assert report["rows"] == []


def test_save_alias_locations_writes(tmp_path):
    ctrl = _controller(tmp_path)
    result = ctrl.save_alias_locations({"OVERRIDE": "/somewhere/else"})
    assert result["changed"] == 1
    assert "OVERRIDE=/somewhere/else" in (tmp_path / "user" / "nwn.ini").read_text()


# -- dialog ---------------------------------------------------------------- #
def test_dialog_lists_and_pending_updates(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.alias_section_editor import AliasSectionEditor

    ctrl = _controller(tmp_path)
    dlg = AliasSectionEditor(ctrl)
    qtbot.addWidget(dlg)
    assert dlg.tree.topLevelItemCount() == 4
    assert dlg.save_button.isEnabled()
    # Edit the OVERRIDE row's value.
    dlg.tree.topLevelItem(2).setText(1, "/edited/override")
    assert dlg.pending_updates() == {"OVERRIDE": "/edited/override"}


def test_dialog_save_confirm_gate(tmp_path, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.dialogs.alias_section_editor import AliasSectionEditor

    ctrl = _controller(tmp_path)
    dlg = AliasSectionEditor(ctrl)
    qtbot.addWidget(dlg)
    dlg.tree.topLevelItem(0).setText(1, "/new/hak")

    # Declining the config-isolation confirm must NOT write nwn.ini.
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg._on_save()
    assert "HAK=./hak" in (tmp_path / "user" / "nwn.ini").read_text()
    assert dlg.changed is False

    # Accepting writes it (and marks changed so the caller re-opens the profile).
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    dlg._on_save()
    assert "HAK=/new/hak" in (tmp_path / "user" / "nwn.ini").read_text()
    assert dlg.changed is True


def test_command_opens_and_enabled(tmp_path, qtbot):
    from vaultkeeper.ui.main_window import MainWindow

    ctrl = _controller(tmp_path)
    win = MainWindow(controller=ctrl)
    qtbot.addWidget(win)
    assert "MsAliasSection" in win.implemented_commands()
    assert win.nit_menu.actions_by_id["MsAliasSection"].isEnabled()
    win._on_command("MsAliasSection")
    assert win._alias_editor.isVisible()
