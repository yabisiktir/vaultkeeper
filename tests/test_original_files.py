"""Original-restorers — CRC-table detection + restorer creation (VB AutoOriginalRestorer)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.state import State
from vaultkeeper.game.original_files import (
    original_crc_table,
    original_source_files,
    restorer_buckets,
    validate_originals,
)
from vaultkeeper.ui.controller import ProfileController


# -- CRC tables ------------------------------------------------------------ #
def test_crc_tables_load_and_normalise():
    classic = original_crc_table(is_ee=False)
    ee = original_crc_table(is_ee=True)
    assert classic["nwn/dialog.tlk"] == 206031260
    # values are unsigned 32-bit.
    assert all(0 <= v <= 0xFFFFFFFF for v in classic.values())
    # The EE table is the classic table plus the EE overrides (VB UseEeOriginal), so it
    # is at least as large and carries the EE-specific CRC for a shared entry.
    from vaultkeeper.game.original_files import _load_table

    ee_only = _load_table("original_ee_files.json")
    assert len(ee) >= len(classic)
    a_key = next(iter(ee_only))
    assert ee[a_key] == ee_only[a_key]  # EE value wins in the merged table


def test_restorer_buckets_group_by_kind():
    fks = [
        FileKeyInfo.installed("nwn", "dialog.tlk"),  # core
        FileKeyInfo.installed("nwn", "nwn.ini"),  # ini
        FileKeyInfo.installed("override", "hero.bic"),  # character
        FileKeyInfo.installed("nwm", "Chapter1.nwm"),  # per-module
    ]
    buckets = restorer_buckets(fks)
    assert (C.RESTORER_GROUP, C.CORE_FILES_RESTORER) in buckets
    assert (C.RESTORER_GROUP, C.INI_FILES_RESTORER) in buckets
    assert (C.RESTORER_GROUP, C.CHARACTER_FILES_RESTORER) in buckets
    assert (C.ORIGINAL_MODS_GROUP, "1. Neverwinter Nights (EE)") in buckets


def test_restorer_buckets_group_modules_as_nit_does():
    """VB AutoOriginalRestorer: one restorer per campaign, one per bundled module,
    each with the edition; never one per chapter file (logic audit 3a)."""
    names = [
        ("nwm", "Chapter1.nwm"), ("nwm", "Chapter1E.nwm"), ("nwm", "Prelude.nwm"),
        ("nwm", "XP1-Chapter 1.nwm"), ("nwm", "XP1-Interlude.nwm"),
        ("nwm", "XP2_Chapter1.nwm"),
        ("nwm", "Neverwinter Nights - Darkness over Daggerford.nwm"),
        ("mod", "Contest Of Champions 0492.mod"), ("mod", "Kingmaker.mod"),
        ("override", "x.2da"),
    ]
    fks = [FileKeyInfo.installed(folder, name) for folder, name in names]

    buckets = {name: sorted(f.filename for f in files)
               for (_g, name), files in restorer_buckets(fks, is_ee=True).items()}

    assert buckets == {
        C.CORE_FILES_RESTORER: ["x.2da"],
        "1. Neverwinter Nights (EE)": ["Chapter1.nwm", "Chapter1E.nwm", "Prelude.nwm"],
        "2. The Shadow of Undrentide (EE)": ["XP1-Chapter 1.nwm", "XP1-Interlude.nwm"],
        "3. Hordes of the Underdark (EE)": ["XP2_Chapter1.nwm"],
        "Darkness over Daggerford (EE)": ["Neverwinter Nights - Darkness over Daggerford.nwm"],
        "Contest of Champions (EE)": ["Contest Of Champions 0492.mod"],
        "Kingmaker (EE)": ["Kingmaker.mod"],
    }


def test_classic_demo_modules_and_other_modules():
    fks = [
        FileKeyInfo.installed("modules", "Demo - The Cat Lady.mod"),
        FileKeyInfo.installed("modules", "Some Other.mod"),
    ]
    buckets = restorer_buckets(fks, is_ee=False, restorer_group=C.GROUP_NONE)
    assert (C.ORIGINAL_MODS_GROUP, "Demo - The Cat Lady (NWN)") in buckets
    # A classic module that is not one of the named ones is a core file.
    assert [f.filename for f in buckets[(C.GROUP_NONE, C.CORE_FILES_RESTORER)]] == [
        "Some Other.mod"
    ]


# -- detection / validation ------------------------------------------------ #
def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _install_original(pd, folder, filename, crc, *, installer=C.INSTALLER_UNKNOWN):
    ifk = FileKeyInfo.installed(folder, filename)
    pd.installed_list[ifk] = InstalledFileData(
        key=ifk,
        file_state=State.INSTALLED,
        extension=Path(filename).suffix,
        file_crc=crc,
        installer=installer,
    )
    return ifk


def test_original_source_files_matches_crc(tmp_path):
    ctrl = _controller(tmp_path)
    table = original_crc_table(is_ee=True)
    _install_original(ctrl.pd, "nwn", "dialog.tlk", table["nwn/dialog.tlk"])
    # A file with the RIGHT name but WRONG crc is not original.
    _install_original(ctrl.pd, "nwn", "nwn.ini", 12345)

    originals = original_source_files(ctrl.pd, ctrl.ctx.mapper, is_ee=True)
    names = {fk.filename for fk in originals}
    assert "dialog.tlk" in names
    assert "nwn.ini" not in names


def test_original_source_files_excludes_mod_owned(tmp_path):
    ctrl = _controller(tmp_path)
    table = original_crc_table(is_ee=True)
    # A file whose CRC matches but is claimed by a real mod is NOT an original source.
    from vaultkeeper.core.mod_data import ModData

    ctrl.pd.add_mod(ModData(group=C.GROUP_NONE, mod_name="SomeMod", mod_state=State.INSTALLED))
    _install_original(
        ctrl.pd, "nwn", "dialog.tlk", table["nwn/dialog.tlk"], installer="SomeMod"
    )
    assert original_source_files(ctrl.pd, ctrl.ctx.mapper, is_ee=True) == []


def test_original_source_files_includes_a_stale_original_restorer_copy(tmp_path):
    # VB OriginalSourceFile: held by an original restorer whose copy differs.
    from vaultkeeper.core.file_data import FileData
    from vaultkeeper.core.mod_data import ModData

    ctrl = _controller(tmp_path)
    table = original_crc_table(is_ee=True)
    restorer = C.CORE_FILES_RESTORER
    ctrl.pd.add_mod(ModData(group=C.RESTORER_GROUP, mod_name=restorer))
    fk = FileKeyInfo(C.RESTORER_GROUP, restorer, "nwn", "dialog.tlk")
    ctrl.pd.add_file(FileData(key=fk, file_state=State.INSTALLED, extension=".tlk", file_crc=1))
    _install_original(
        ctrl.pd, "nwn", "dialog.tlk", table["nwn/dialog.tlk"], installer=restorer
    )

    names = {k.filename for k in original_source_files(ctrl.pd, ctrl.ctx.mapper, is_ee=True)}
    assert "dialog.tlk" in names

    ctrl.pd.file_list[fk].file_crc = table["nwn/dialog.tlk"]
    assert original_source_files(ctrl.pd, ctrl.ctx.mapper, is_ee=True) == []


def test_validate_originals_relabels_unknown(tmp_path):
    ctrl = _controller(tmp_path)
    table = original_crc_table(is_ee=True)
    ifk = _install_original(ctrl.pd, "nwn", "dialog.tlk", table["nwn/dialog.tlk"])
    assert ctrl.pd.installed_list[ifk].installer == C.INSTALLER_UNKNOWN
    changed = validate_originals(ctrl.pd, ctrl.ctx.mapper, is_ee=True)
    assert changed == 1
    assert ctrl.pd.installed_list[ifk].installer == C.INSTALLER_ORIGINAL


# -- controller create_original_restorers ---------------------------------- #
def test_create_original_restorers_builds_restorer_mod(tmp_path):
    ctrl = _controller(tmp_path)
    table = original_crc_table(is_ee=True)
    # Put a real dialog.tlk in the game root (folder "nwn" -> game_root).
    game_root = ctrl.ctx.game_folders["nwn"]
    game_root.mkdir(parents=True, exist_ok=True)
    (game_root / "dialog.tlk").write_bytes(b"the original dialog table")
    _install_original(ctrl.pd, "nwn", "dialog.tlk", table["nwn/dialog.tlk"])

    result = ctrl.create_original_restorers()
    assert result["created"] == 1
    assert result["files"] == 1

    restorer = ctrl.pd.mod_item(C.CORE_FILES_RESTORER)
    assert restorer is not None and restorer.is_restorer()
    assert restorer.group == C.RESTORER_GROUP
    # The original file was copied into the restorer's payload.
    dest = (
        ctrl.ctx.profile_mods_dir
        / C.CORE_FILES_RESTORER
        / C.MOD_INSTALLER_DIR
        / "nwn"
        / "dialog.tlk"
    )
    assert dest.is_file()


def test_create_original_restorers_none_found(tmp_path):
    ctrl = _controller(tmp_path)
    result = ctrl.create_original_restorers()
    assert result["created"] == 0
    assert "No pristine" in result["message"]


def test_command_wired_and_enabled(tmp_path, qtbot):
    from vaultkeeper.ui.main_window import MainWindow

    ctrl = _controller(tmp_path)
    win = MainWindow(controller=ctrl)
    qtbot.addWidget(win)
    assert "MsCreateOriginalRestorers" in win.implemented_commands()
    assert win.nit_menu.actions_by_id["MsCreateOriginalRestorers"].isEnabled()
    win._on_command("MsCreateOriginalRestorers")  # no pristine files -> just a status msg
