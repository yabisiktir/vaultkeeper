"""Create Restorer backs up installed files no mod owns (VB ``MsCreateRestorer``).

NIT gathers ``pd.UnknownSourceFiles`` — files in the game that no installer or
restorer owns — into a restorer the user names. The restorer owns them, so when
a mod that overwrote one is uninstalled, the anneal puts the original back.
Vaultkeeper's Create Restorer only tagged the selected mod, so a user's own
override file was lost (logic audit, docs/logic_audit/stage2_findings.md R1).
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


def _users_own_file(tmp_path: Path) -> Path:
    own = tmp_path / "NWN" / "override" / "shared.2da"
    own.parent.mkdir(parents=True)
    own.write_text("ORIGINAL")
    return own


def _alpha(c: ProfileController, tmp_path: Path) -> None:
    c.create_mod("Alpha Pack")
    folder = tmp_path / "Profiles" / "P" / "Alpha Pack"
    (folder / "shared.2da").write_text("ALPHA")
    (folder / "alpha.hak").write_text("A")
    assert c.build_installer_payload("Alpha Pack")["ok"]


def test_unowned_file_is_backed_up_and_restored_after_uninstall(tmp_path: Path) -> None:
    own = _users_own_file(tmp_path)
    c = _controller(tmp_path)
    assert any(fk.filename == "shared.2da" for fk in c.unowned_source_files())

    result = c.create_restorer_from_installed("My Originals")

    assert result["ok"] and result["files"] >= 1
    md = c.pd.mod_item("My Originals")
    assert md is not None and md.is_restorer()
    assert md.group == C.RESTORER_GROUP
    backup = tmp_path / "Profiles" / "P" / "My Originals" / C.MOD_INSTALLER_DIR / "override"
    assert (backup / "shared.2da").read_text() == "ORIGINAL"
    assert not any(fk.filename == "shared.2da" for fk in c.unowned_source_files())

    _alpha(c, tmp_path)
    c.install(["Alpha Pack"])
    # Whether Alpha's copy shows while it is installed depends on group priority
    # (natural sort of "......001" vs "000.  Restorers"); what the restorer
    # guarantees is that uninstalling Alpha leaves the user's original in place.
    c.uninstall(["Alpha Pack"])
    assert own.read_text() == "ORIGINAL"


def test_nothing_unowned_means_nothing_to_create(tmp_path: Path) -> None:
    c = _controller(tmp_path)

    result = c.create_restorer_from_installed("My Originals")

    assert not result["ok"]
    assert "no need to create a Restorer" in result["message"]
    assert c.pd.mod_item("My Originals") is None


def test_existing_restorer_name_adds_files_but_a_mod_name_is_refused(tmp_path: Path) -> None:
    _users_own_file(tmp_path)
    c = _controller(tmp_path)
    _alpha(c, tmp_path)

    refused = c.create_restorer_from_installed("Alpha Pack")
    assert not refused["ok"]

    assert c.create_restorer_from_installed("My Originals")["ok"]
    later = tmp_path / "NWN" / "override" / "later.2da"
    later.write_text("LATER")
    c.rescan_installed_state()
    added = c.create_restorer_from_installed("My Originals")
    assert added["ok"], added["message"]
    backup = tmp_path / "Profiles" / "P" / "My Originals" / C.MOD_INSTALLER_DIR / "override"
    assert (backup / "later.2da").read_text() == "LATER"


def test_mod_that_outranks_the_restorer_overwrites_then_uninstall_restores(
    tmp_path: Path,
) -> None:
    own = _users_own_file(tmp_path)
    c = _controller(tmp_path)
    assert c.create_restorer_from_installed("My Originals")["ok"]
    _alpha(c, tmp_path)
    # "100.  Community Packs" sorts after "000.  Restorers": Alpha wins while installed.
    c.move_to_group(["Alpha Pack"], "100.  Community Packs")

    c.install(["Alpha Pack"])
    assert own.read_text() == "ALPHA"

    c.uninstall(["Alpha Pack"])
    assert own.read_text() == "ORIGINAL"


def test_create_restorer_command_backs_up_unowned_files(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from vaultkeeper.ui.main_window import MainWindow

    _users_own_file(tmp_path)
    win = MainWindow(_controller(tmp_path))
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "_offer_character_restorer", lambda: False)
    asked = []
    monkeypatch.setattr(
        QInputDialog, "getText", lambda *a, **k: (asked.append(a[2]) or ("My Originals", True))
    )

    win._on_create_restorer()

    assert asked and "belong to no mod" in asked[0]
    md = win.controller.pd.mod_item("My Originals")
    assert md is not None and md.is_restorer()

    # Nothing left to back up: the command says so and creates nothing.
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[2]))
    win._on_create_restorer()
    assert told and "no need to create a Restorer" in told[0]
