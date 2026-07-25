"""Tests for creating an isolated NWN folder for a profile (VB CreateNwnFolder)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game.create_nwn_folder import (
    create_nwn_folder,
    default_target,
)


def _make_source(root: Path) -> Path:
    src = root / "NWN"
    (src / "data").mkdir(parents=True)
    (src / "data" / "base.bif").write_bytes(b"BIF")
    (src / "nwnmain.exe").write_bytes(b"EXE")
    (src / "nwn.ini").write_text("[Alias]\n")
    return src


def test_copies_source_contents_not_root(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    target = tmp_path / "profiles" / "MyProfile"

    result = create_nwn_folder(target, src, is_ee=True)
    assert result.ok
    # The source's contents land directly in target (source root not nested).
    assert (target / "nwnmain.exe").is_file()
    assert (target / "data" / "base.bif").read_bytes() == b"BIF"
    assert not (target / "NWN").exists()


def test_empty_source_aborts_and_cleans_up(tmp_path: Path) -> None:
    src = tmp_path / "empty"
    src.mkdir()
    target = tmp_path / "new"
    result = create_nwn_folder(target, src)
    assert result.status == "abort"
    assert "empty" in result.message.lower()
    assert not target.exists()  # freshly-created target removed


def test_missing_source_aborts(tmp_path: Path) -> None:
    result = create_nwn_folder(tmp_path / "new", tmp_path / "nope")
    assert result.status == "abort"


def test_target_inside_source_rejected(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    result = create_nwn_folder(src / "sub", src)
    assert result.status == "abort"
    assert "outside" in result.message.lower()


def test_classic_copies_config_ini(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    config_src = tmp_path / "config"
    config_src.mkdir()
    (config_src / "nwn.ini").write_text("[classic]\n")
    target = tmp_path / "classic_profile"

    result = create_nwn_folder(
        target, src, is_ee=False, config_ini_source=config_src
    )
    assert result.ok
    # Target already got nwn.ini from the source copy; the classic step is a no-op
    # here, but the file is present.
    assert (target / "nwn.ini").is_file()


def test_classic_config_ini_pulled_when_source_lacks_it(tmp_path: Path) -> None:
    # Source without nwn.ini; classic step pulls it from the config source.
    src = tmp_path / "NWN"
    src.mkdir()
    (src / "nwnmain.exe").write_bytes(b"EXE")
    config_src = tmp_path / "config"
    config_src.mkdir()
    (config_src / "nwn.ini").write_text("[classic]\n")
    target = tmp_path / "classic_profile"

    result = create_nwn_folder(target, src, is_ee=False, config_ini_source=config_src)
    assert result.ok
    assert (target / "nwn.ini").read_text() == "[classic]\n"


def test_default_target_naming(tmp_path: Path) -> None:
    ee = default_target(tmp_path, "Adventures", is_ee=True)
    assert ee == tmp_path / "NeverwinterNights EE" / "Adventures"
    classic = default_target(tmp_path, "Adventures", is_ee=False)
    assert classic == tmp_path / "NeverwinterNights" / "Adventures"


def test_dialog_creates_and_returns_path(qtbot, tmp_path: Path, monkeypatch) -> None:
    from vaultkeeper.ui.dialogs import create_nwn_folder as mod
    from vaultkeeper.ui.dialogs.create_nwn_folder import CreateNwnFolderDialog

    src = _make_source(tmp_path)
    target = tmp_path / "out" / "Profile"

    yes = mod.QMessageBox.StandardButton.Yes
    monkeypatch.setattr(mod.QMessageBox, "question", lambda *a, **k: yes)
    monkeypatch.setattr(mod.QMessageBox, "information", lambda *a, **k: None)

    dlg = CreateNwnFolderDialog(source=str(src), is_ee=True)
    qtbot.addWidget(dlg)
    dlg._target.setText(str(target))
    dlg._on_create()

    assert dlg.created_path == str(target)
    assert (target / "nwnmain.exe").is_file()
