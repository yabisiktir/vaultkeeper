"""NIT's managed "(Auto)" restorers (VB ``RunAutoRestorers``).

NIT keeps four restorers in "ZZZ.  NIT Managed Restorers (Auto)" current as you
play: database files, the game's INI files (plus settings.tml), character
journals, and unowned nitconfig identifiers. Vaultkeeper had only the character
restorer (logic audit, docs/logic_audit/stage2_findings.md S2).
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True, exist_ok=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _game(tmp_path: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = tmp_path / "NWN" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def _backup(tmp_path: Path, restorer: str, folder: str, name: str) -> Path:
    return tmp_path / "Profiles" / "P" / restorer / C.MOD_INSTALLER_DIR / folder / name


GAME = {
    "nwn.ini": "[Alias]\nHAK=hak\n",
    "settings.tml": "[game]\n",
    "database/campaign.sqlite3": "DB",
    "localvault/hero.txt": "journal",
    "nitconfig/Gone Mod.nitins": "",
}


def test_first_run_creates_the_four_restorers(tmp_path: Path) -> None:
    _game(tmp_path, GAME)
    c = _controller(tmp_path)

    result = c.run_auto_restorers()

    assert result["ini"] == 2 and result["database"] == 1
    assert result["journal"] == 1 and result["config"] == 1
    for name in (C.AUTO_INI_FILES, C.AUTO_DATABASE, C.AUTO_JOURNAL_FILES, C.AUTO_NIT_CONFIG):
        md = c.pd.mod_item(name)
        assert md is not None and md.is_restorer(), name
        assert md.group == C.AUTO_GROUP
    assert _backup(tmp_path, C.AUTO_INI_FILES, "nwn", "nwn.ini").read_text() == GAME["nwn.ini"]
    assert _backup(tmp_path, C.AUTO_DATABASE, "database", "campaign.sqlite3").read_text() == "DB"
    assert _backup(tmp_path, C.AUTO_JOURNAL_FILES, "localvault", "hero.txt").exists()
    assert _backup(tmp_path, C.AUTO_NIT_CONFIG, "nitconfig", "Gone Mod.nitins").exists()
    assert "Restorer files updated" in result["message"]


def test_nothing_changed_means_nothing_to_do(tmp_path: Path) -> None:
    _game(tmp_path, GAME)
    c = _controller(tmp_path)
    c.run_auto_restorers()

    again = c.run_auto_restorers()

    assert (again["ini"], again["database"], again["journal"], again["config"]) == (0, 0, 0, 0)
    assert again["message"] == ""


def test_a_rewritten_ini_file_is_backed_up_again(tmp_path: Path) -> None:
    _game(tmp_path, GAME)
    c = _controller(tmp_path)
    c.run_auto_restorers()

    (tmp_path / "NWN" / "nwn.ini").write_text("[Alias]\nHAK=hak\n[Display]\nWidth=1920\n")
    result = c.run_auto_restorers()

    assert result["ini"] == 1
    backup = _backup(tmp_path, C.AUTO_INI_FILES, "nwn", "nwn.ini")
    assert "Width=1920" in backup.read_text()


def test_a_deleted_database_file_loses_its_backup(tmp_path: Path, recycle_bin: Path) -> None:
    _game(tmp_path, GAME)
    c = _controller(tmp_path)
    c.run_auto_restorers()

    (tmp_path / "NWN" / "database" / "campaign.sqlite3").unlink()
    c.rescan_installed_state()
    c.run_auto_restorers()

    assert not _backup(tmp_path, C.AUTO_DATABASE, "database", "campaign.sqlite3").exists()
    md = c.pd.mod_item(C.AUTO_DATABASE)
    assert all(fk.filename != "campaign.sqlite3" for fk in md.files)
    assert any(recycle_bin.iterdir())


def test_config_restorer_goes_once_its_identifiers_have_owners(tmp_path: Path) -> None:
    _game(tmp_path, {"nitconfig/Gone Mod.nitins": ""})
    c = _controller(tmp_path)
    assert c.run_auto_restorers()["config"] == 1

    # The mod comes back and owns its identifier again.
    c.create_mod("Gone Mod")
    (tmp_path / "Profiles" / "P" / "Gone Mod" / "gone.hak").write_text("H")
    assert c.build_installer_payload("Gone Mod")["ok"]
    c.install(["Gone Mod"])
    c.run_auto_restorers()

    assert c.pd.mod_item(C.AUTO_NIT_CONFIG) is None
    assert not (tmp_path / "Profiles" / "P" / C.AUTO_NIT_CONFIG).exists()
    # …and it does not come straight back for its own leftover identifier.
    assert c.run_auto_restorers()["config"] == 0
    assert c.pd.mod_item(C.AUTO_NIT_CONFIG) is None


def test_finishing_a_game_updates_the_auto_restorers(qtbot, tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime

    from vaultkeeper.ui.main_window import MainWindow

    _game(tmp_path, {"nwn.ini": "[Alias]\n"})
    c = _controller(tmp_path)
    win = MainWindow(c)
    qtbot.addWidget(win)
    monkeypatch.setattr(c, "process_play_session", lambda *_: {"mods": {}})
    win._play_started = datetime.now()

    win._on_game_exited()

    assert c.pd.mod_item(C.AUTO_INI_FILES) is not None


def test_user_restorer_names_cannot_take_an_auto_name(qtbot, tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog

    from vaultkeeper.ui.main_window import MainWindow

    _game(tmp_path, {"override/mine.2da": "MINE"})
    win = MainWindow(_controller(tmp_path))
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "_offer_character_restorer", lambda: False)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Sneaky (Auto)", True))

    win._on_create_restorer()

    assert win.controller.pd.mod_item("Sneaky (Auto)") is None
