"""Moving the store to another folder (VB Settings › Locations, MoveNitStore)."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from vaultkeeper.store_move import (
    STORE_FOLDER,
    _rewrite_text,
    check_target,
    move_store,
    recycle_old_store,
    rewrite_settings_paths,
    target_for,
)


def _store(root: Path) -> Path:
    """A small store: a mod file, a database that names it by absolute path, an
    empty profile folder."""
    mod = root / "Profiles" / "EE" / "Alpha" / ".Mod Installer" / "hak" / "a.hak"
    mod.parent.mkdir(parents=True)
    mod.write_bytes(b"HAK V1.0" * 100)
    (root / "Profiles" / "Empty").mkdir(parents=True)
    data = root / "Data"
    data.mkdir()
    (data / "EE.json").write_text(json.dumps({"mods": ["Alpha"]}))
    (data / "GameMapData.json").write_text(json.dumps({"module": str(mod)}))
    return root


def _recycler(bin_dir: Path):
    bin_dir.mkdir(exist_ok=True)
    def recycle(path: str) -> None:
        Path(path).rename(bin_dir / Path(path).name)
    return recycle


# -- where it may go ---------------------------------------------------------- #
def test_the_store_goes_in_its_own_folder_inside_the_chosen_one(tmp_path) -> None:
    assert target_for(tmp_path / "Games") == tmp_path / "Games" / STORE_FOLDER
    assert target_for(tmp_path / STORE_FOLDER) == tmp_path / STORE_FOLDER


def test_refused_targets(tmp_path) -> None:
    store = _store(tmp_path / "Store")
    assert check_target(store, store / "Profiles")  # inside the store
    busy = tmp_path / "Busy" / STORE_FOLDER
    busy.mkdir(parents=True)
    (busy / "something").write_text("x")
    assert check_target(store, tmp_path / "Busy")  # not empty
    assert check_target(store, tmp_path / "New") == ""
    (tmp_path / "Empty" / STORE_FOLDER).mkdir(parents=True)
    assert check_target(store, tmp_path / "Empty") == ""  # an empty folder is fine


# -- path rewriting ----------------------------------------------------------- #
def test_only_whole_path_prefixes_are_rewritten() -> None:
    old, new = PurePosixPath("/a/Store"), PurePosixPath("/b/Vaultkeeper Store")
    text = json.dumps(["/a/Store/x.mod", "/a/Store", "/a/Store2/y.mod", "/c/a/Store/z"])
    assert json.loads(_rewrite_text(text, old, new)) == [
        "/b/Vaultkeeper Store/x.mod", "/b/Vaultkeeper Store", "/a/Store2/y.mod", "/c/a/Store/z",
    ]


def test_windows_paths_are_rewritten_too() -> None:
    old = PureWindowsPath(r"C:\Users\me\AppData\Local\Vaultkeeper\Store")
    new = PureWindowsPath(r"D:\Games\Vaultkeeper Store")
    text = json.dumps({"module": str(old) + r"\Profiles\EE\x.mod"})
    assert json.loads(_rewrite_text(text, old, new)) == {
        "module": r"D:\Games\Vaultkeeper Store\Profiles\EE\x.mod"
    }


def test_a_windows_path_saved_with_forward_slashes_is_rewritten_too() -> None:
    """Qt's file dialogs hand back C:/... while Python writes C:\\..."""
    old = PureWindowsPath(r"C:\Users\me\Store")
    new = PureWindowsPath(r"D:\Vaultkeeper Store")
    text = json.dumps(["C:/Users/me/Store/Tools/x.exe", r"C:\Users\me\Store\a.mod"])
    assert json.loads(_rewrite_text(text, old, new)) == [
        "D:/Vaultkeeper Store/Tools/x.exe", r"D:\Vaultkeeper Store\a.mod",
    ]


def test_settings_paths_into_the_store_move_with_it() -> None:
    data = {"run_links": [{"path": "/a/Store/Tools/x.exe"}], "nwn_path": "/games/nwn"}
    out = rewrite_settings_paths(data, PurePosixPath("/a/Store"), PurePosixPath("/b/S"))
    assert out == {"run_links": [{"path": "/b/S/Tools/x.exe"}], "nwn_path": "/games/nwn"}


# -- the move ----------------------------------------------------------------- #
def test_the_store_is_copied_checked_and_its_paths_rewritten(tmp_path) -> None:
    store = _store(tmp_path / "Store")
    recycle = _recycler(tmp_path / "bin")
    result = move_store(store, tmp_path / "New", recycle=recycle)
    assert result.ok, result.message
    target = tmp_path / "New" / STORE_FOLDER
    assert result.store == target
    hak = target / "Profiles" / "EE" / "Alpha" / ".Mod Installer" / "hak" / "a.hak"
    assert hak.read_bytes() == b"HAK V1.0" * 100
    assert (target / "Profiles" / "Empty").is_dir()
    module = json.loads((target / "Data" / "GameMapData.json").read_text())["module"]
    assert module.startswith(str(target))
    # The old store is untouched until the caller has saved the switch.
    old_map = json.loads((store / "Data" / "GameMapData.json").read_text())
    assert old_map["module"].startswith(str(store))
    assert not (tmp_path / "New" / (STORE_FOLDER + ".moving")).exists()


def test_cancelling_leaves_the_old_store_and_no_copy(tmp_path) -> None:
    store = _store(tmp_path / "Store")
    result = move_store(
        store, tmp_path / "New", recycle=_recycler(tmp_path / "bin"),
        on_progress=lambda done, total: False,
    )
    assert not result.ok
    assert result.store == store
    assert not (tmp_path / "New" / STORE_FOLDER).exists()
    assert not (tmp_path / "New" / (STORE_FOLDER + ".moving")).exists()
    assert (store / "Data" / "EE.json").is_file()


def test_a_file_that_does_not_copy_whole_stops_the_move(tmp_path, monkeypatch) -> None:
    import shutil

    store = _store(tmp_path / "Store")
    real = shutil.copy2

    def short_copy(src, dst):
        real(src, dst)
        if str(src).endswith(".hak"):
            Path(dst).write_bytes(b"short")

    monkeypatch.setattr("vaultkeeper.store_move.shutil.copy2", short_copy)
    result = move_store(store, tmp_path / "New", recycle=_recycler(tmp_path / "bin"))
    assert not result.ok and "did not copy correctly" in result.message
    assert not (tmp_path / "New" / STORE_FOLDER).exists()
    assert (store / "Profiles" / "EE" / "Alpha" / ".Mod Installer" / "hak" / "a.hak").is_file()


def test_the_old_store_goes_to_the_recycle_bin_only_when_asked(tmp_path) -> None:
    store = _store(tmp_path / "Store")
    bin_dir = tmp_path / "bin"
    assert "recycle bin" in recycle_old_store(store, _recycler(bin_dir))
    assert (bin_dir / "Store" / "Data" / "EE.json").is_file()

    def broken(_path):
        raise OSError("no trash here")

    assert "still at" in recycle_old_store(tmp_path, broken)


# -- start-up and Settings ---------------------------------------------------- #
def test_a_pending_move_runs_at_start_up(qtbot, tmp_path, recycle_bin, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.ui import app

    store = _store(tmp_path / "Store")
    settings = load_settings()
    settings.store_root = str(store)
    settings.store_move_to = str(tmp_path / "New")
    settings.run_links = [{"text": "Tool", "path": str(store / "Tools" / "x.exe")}]
    save_settings(settings)
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: shown.append(a[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: pytest.fail(a[2]))

    app._apply_pending_store_move()

    after = load_settings()
    target = tmp_path / "New" / STORE_FOLDER
    assert after.store_root == str(target)
    assert after.store_move_to == ""
    assert after.run_links[0]["path"] == str(target / "Tools" / "x.exe")
    assert (target / "Data" / "EE.json").is_file()
    assert not store.exists()
    assert (recycle_bin / "Store" / "Data" / "EE.json").is_file()
    assert "recycle bin" in shown[0]


def test_a_failed_move_keeps_the_old_store_and_forgets_the_request(
    qtbot, tmp_path, monkeypatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.ui import app

    store = _store(tmp_path / "Store")
    settings = load_settings()
    settings.store_root = str(store)
    settings.store_move_to = str(store / "Profiles")  # inside the store: refused
    save_settings(settings)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warned.append(a[2]))

    app._apply_pending_store_move()

    after = load_settings()
    assert after.store_root == str(store)
    assert after.store_move_to == ""
    assert warned and (store / "Data" / "EE.json").is_file()


def test_settings_locations_schedules_and_cancels_a_move(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    store = _store(tmp_path / "Store")
    dlg = SettingsDialog(Settings(store_root=str(store)))
    qtbot.addWidget(dlg)
    row = dlg._build_store_row()
    qtbot.addWidget(row)
    assert dlg.store_edit.text() == str(store)
    assert not dlg.store_move_label.isVisibleTo(row)

    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warned.append(a[2]))
    monkeypatch.setattr(dlg, "_choose_store_folder", lambda: str(store / "Data"))
    dlg._on_move_store()
    assert warned and dlg._pending_store_move == ""

    monkeypatch.setattr(dlg, "_choose_store_folder", lambda: str(tmp_path / "New"))
    dlg._on_move_store()
    assert dlg.store_move_label.isVisibleTo(row)
    assert str(tmp_path / "New" / STORE_FOLDER) in dlg.store_move_label.text()
    settings = Settings()
    dlg.apply_to(settings)
    assert settings.store_move_to == str(tmp_path / "New")

    dlg.store_cancel_button.click()  # Don't Move
    dlg.apply_to(settings)
    assert settings.store_move_to == ""
