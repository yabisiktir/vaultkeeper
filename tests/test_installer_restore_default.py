"""Rebuilding an installed mod's installer puts it back (VB ``BehaviourInstallerRestore``).

NIT's default is True: Create Installer uninstalls an installed mod, rebuilds it,
and reinstalls it, so the game gets the new version at once. Vaultkeeper ported
the setting as False, so a rebuilt mod was left uninstalled (logic audit,
docs/logic_audit/stage2_findings.md U2). Every field is saved to settings.json,
so existing files are migrated once (settings version 2).
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.persistence.json_store import read_json, write_json
from vaultkeeper.ui.controller import ProfileController


def test_installer_restore_is_on_by_default() -> None:
    assert Settings().installer_restore is True


def test_version_1_settings_turn_installer_restore_on_once(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    write_json(path, {"version": 1, "installer_restore": False, "nwn_path": "/g"})

    loaded = load_settings(path)

    assert loaded.installer_restore is True
    assert loaded.nwn_path == "/g"
    save_settings(loaded, path)
    assert read_json(path)["version"] >= 2


def test_a_deliberate_off_after_migration_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    write_json(path, {"version": 2, "installer_restore": False})

    assert load_settings(path).installer_restore is False


def test_create_installer_reinstalls_a_rebuilt_installed_mod(qtbot, tmp_path, monkeypatch) -> None:
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Alpha Pack")
    source = profile_mods / "Alpha Pack"
    (source / "alpha.hak").write_text("v1")
    (source / "old.hak").write_text("old")
    assert c.build_installer_payload("Alpha Pack")["ok"]
    c.install(["Alpha Pack"])

    (source / "alpha.hak").write_text("v2")
    (source / "old.hak").unlink()
    win = MainWindow(c)
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "selected_mod_names", lambda: ["Alpha Pack"])

    win._on_create_installer()

    hak = c.ctx.game_folders["hak"]
    assert c.pd.mod_item("Alpha Pack").installed
    assert (hak / "alpha.hak").read_text() == "v2"
    assert not (hak / "old.hak").exists()


def test_create_installer_shows_the_builds_phases(qtbot, tmp_path, monkeypatch) -> None:
    """VB CreateInstaller shows what it is doing; the build's phases reach a progress window."""
    from PySide6.QtWidgets import QProgressDialog

    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Alpha Pack")
    (profile_mods / "Alpha Pack" / "alpha.hak").write_text("v1")
    win = MainWindow(c)
    qtbot.addWidget(win)
    labels: list[str] = []
    monkeypatch.setattr(
        QProgressDialog, "setLabelText", lambda self, text: labels.append(text)
    )

    win._on_create_installer(["Alpha Pack"])

    assert any("Alpha Pack" in t and "Building the installer" in t for t in labels)


def _two_file_mod(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Alpha Pack")
    for name in ("a.hak", "b.hak", "c.hak"):
        (profile_mods / "Alpha Pack" / name).write_text(name)
    return c


def test_cancelling_a_build_keeps_what_was_copied_as_nit_does(tmp_path: Path) -> None:
    """VB CreateInstaller Cancel: stop, keep the partial installer, warn it may be incomplete."""
    c = _two_file_mod(tmp_path)
    asked = []

    result = c.build_installer_payload(
        "Alpha Pack", cancelled=lambda: asked.append(1) or len(asked) > 2
    )

    assert result["cancelled"] and not result["ok"]
    assert 0 < result["copied"] < 3
    assert "may be incomplete" in result["message"]
    installer = tmp_path / "Profiles" / "P" / "Alpha Pack" / ".Mod Installer" / "hak"
    assert len(list(installer.glob("*.hak"))) == result["copied"]
    assert c.pd.mod_item("Alpha Pack").is_installer(), "a partial installer is still one"


def test_cancelling_before_anything_is_copied_leaves_no_installer(tmp_path: Path) -> None:
    c = _two_file_mod(tmp_path)

    result = c.build_installer_payload("Alpha Pack", cancelled=lambda: True)

    assert result["cancelled"] and result["copied"] == 0
    assert not c.pd.mod_item("Alpha Pack").is_installer()


def test_create_installer_stops_the_batch_on_cancel(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.ui.main_window import MainWindow

    c = _two_file_mod(tmp_path)
    win = MainWindow(c)
    qtbot.addWidget(win)
    built, warned = [], []
    monkeypatch.setattr(
        c, "build_installer_payload",
        lambda name, **_k: built.append(name) or {"ok": False, "cancelled": True,
                                                  "copied": 0, "message": "cancelled"},
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **_k: warned.append(a[2]))
    monkeypatch.setattr(win, "_run_installer_wizard", lambda _n: (None, None))

    win._on_create_installer(["Alpha Pack", "Beta Pack"])

    assert built == ["Alpha Pack"]
    assert warned == ["Mod Installer creation was cancelled - Installer/s may be incomplete."]
