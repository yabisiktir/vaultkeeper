"""Update Enhanced Edition Files (VB MsUpdateEeFiles / updatedeefiles.htm).

The bundled CRC table is a snapshot of one version of the game. After Beamdog or
Steam patches it, every file the patch touched stops matching — and a file that
does not match its table entry is treated as one a mod changed, which is how
Create Original Restorers comes to skip half the game.

pd.original_ee_files existed all along, was persisted, and was read by nothing:
the table this command fills in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core.crc import crc32_file
from vaultkeeper.game import original_files as of
from vaultkeeper.ui.controller import ProfileController


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    # All five shipped folders are in the *install* — mod/mus/nwm/txpk under
    # data/, and ovr beside it. That is the "Enhanced Edition Library directory"
    # the help names, and it is not where mods go; putting them in the user dir
    # is why this scanned nothing the first time.
    game = tmp_path / "NWN"
    user = tmp_path / "user"
    user.mkdir(parents=True)
    for folder in ("mod", "mus"):
        (game / "data" / folder).mkdir(parents=True)
    (game / "ovr").mkdir(parents=True)
    (game / "data" / "mod" / "prelude.mod").write_bytes(b"chapter one")
    (game / "data" / "mus" / "theme.bmu").write_bytes(b"la la")
    (game / "ovr" / "patch.2da").write_bytes(b"rows")

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game,
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=user,
    )


def test_the_scan_covers_the_folders_the_game_ships(controller):
    scanned = of.scan_ee_originals(controller.ctx.game_folders)
    assert set(scanned) >= {"mod/prelude.mod", "mus/theme.bmu", "ovr/patch.2da"}
    shipped = controller.ctx.game_root / "data"
    assert scanned["mod/prelude.mod"] == crc32_file(shipped / "mod" / "prelude.mod")


def test_new_and_changed_are_told_apart():
    known = {"mod/a.mod": 111, "mod/b.mod": 222}
    scanned = {"mod/a.mod": 111, "mod/b.mod": 999, "mod/c.mod": 333}

    changes = of.ee_original_changes(scanned, known=known)
    assert changes["changed"] == {"mod/b.mod": 999}
    assert changes["added"] == {"mod/c.mod": 333}


def test_a_folder_that_was_not_scanned_is_not_reported_as_lost():
    """A Steam install with no ovr would otherwise look like the game had
    misplaced half its files."""
    changes = of.ee_original_changes({"mod/a.mod": 1}, known={"mod/a.mod": 1, "ovr/x": 2})
    assert changes == {"added": {}, "changed": {}}


def test_the_profile_learns_the_new_checksums(controller):
    result = controller.update_ee_files()

    assert result["ok"] and result["added"] == 3
    assert "3 new" in result["message"]
    assert controller.pd.original_ee_files["mod/prelude.mod"] == crc32_file(
        controller.ctx.game_root / "data" / "mod" / "prelude.mod"
    )


def test_running_it_twice_finds_nothing_the_second_time(controller):
    controller.update_ee_files()
    again = controller.update_ee_files()
    assert again["added"] == 0 and again["changed"] == 0
    assert "Nothing has changed" in again["message"]


def test_a_patched_file_is_picked_up_as_changed(controller):
    controller.update_ee_files()
    (controller.ctx.game_root / "data" / "mod" / "prelude.mod").write_bytes(b"patched!")

    result = controller.update_ee_files()
    assert result["changed"] == 1 and result["added"] == 0


def test_what_it_learns_reaches_the_table_that_uses_it(controller):
    """The whole point: pd.original_ee_files was written and read by nothing."""
    controller.update_ee_files()
    table = of.original_crc_table(
        is_ee=True, overrides=dict(controller.pd.original_ee_files)
    )
    assert table["mod/prelude.mod"] == crc32_file(
        controller.ctx.game_root / "data" / "mod" / "prelude.mod"
    )


def test_a_classic_profile_has_nothing_to_do(tmp_path):
    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        is_ee=False,
    )
    result = c.update_ee_files()
    assert result["ok"] and "not an Enhanced Edition" in result["message"]


def test_the_command_is_live(qtbot, controller):
    from vaultkeeper.ui.main_window import MainWindow

    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert "MsUpdateEeFiles" in win.implemented_commands()
