"""Hak Patch editor — order the patch-hak load sequence (VB HakPatchEditor)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_data import InstalledFileData
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.hak_patch import read_patch_sequence
from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, *patch_haks: str) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    ctrl = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    for name in patch_haks:
        ifk = FileKeyInfo.installed("patch", f"{name}.hak")
        ctrl.pd.installed_list[ifk] = InstalledFileData(
            key=ifk, file_state=State.INSTALLED, extension=".hak"
        )
    return ctrl


# -- controller ------------------------------------------------------------ #
def test_patch_hak_sequence_lists_installed(tmp_path):
    ctrl = _controller(tmp_path, "bbb", "aaa")
    # No saved sequence yet -> installed haks in sorted order.
    assert ctrl.patch_hak_sequence() == ["aaa", "bbb"]


def test_saved_order_is_respected(tmp_path):
    ctrl = _controller(tmp_path, "aaa", "bbb", "ccc")
    ctrl.save_patch_hak_sequence(["ccc", "aaa", "bbb"])
    assert ctrl.patch_hak_sequence() == ["ccc", "aaa", "bbb"]
    # Persisted to the NIT sequence file.
    assert read_patch_sequence(ctrl._profile_data_dir()) == ["ccc", "aaa", "bbb"]


def test_save_regenerates_nwnpatch_ini(tmp_path):
    ctrl = _controller(tmp_path, "aaa", "bbb")
    ctrl.save_patch_hak_sequence(["bbb", "aaa"])
    patch_ini = ctrl.ctx.game_root / C.PATCH_INI_FILE
    lines = patch_ini.read_text().splitlines()
    assert lines == ["[Patch]", "PatchFile000=bbb", "PatchFile001=aaa"]


def test_newly_installed_hak_appended(tmp_path):
    ctrl = _controller(tmp_path, "aaa", "bbb")
    ctrl.save_patch_hak_sequence(["bbb", "aaa"])
    # A new patch hak appears after the sequence was saved.
    ifk = FileKeyInfo.installed("patch", "zzz.hak")
    ctrl.pd.installed_list[ifk] = InstalledFileData(
        key=ifk, file_state=State.INSTALLED, extension=".hak"
    )
    assert ctrl.patch_hak_sequence() == ["bbb", "aaa", "zzz"]


# -- dialog ---------------------------------------------------------------- #
def test_dialog_lists_and_reorders(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.hak_patch_editor import HakPatchEditor

    ctrl = _controller(tmp_path, "aaa", "bbb", "ccc")
    dlg = HakPatchEditor(ctrl)
    qtbot.addWidget(dlg)
    assert dlg.order() == ["aaa", "bbb", "ccc"]
    dlg.list.setCurrentRow(2)
    dlg._move(-1)
    assert dlg.order() == ["aaa", "ccc", "bbb"]
    # Save writes the new order.
    dlg._on_save()
    assert ctrl.patch_hak_sequence() == ["aaa", "ccc", "bbb"]


def test_dialog_disables_save_below_two(tmp_path, qtbot):
    from vaultkeeper.ui.dialogs.hak_patch_editor import HakPatchEditor

    ctrl = _controller(tmp_path, "only")
    dlg = HakPatchEditor(ctrl)
    qtbot.addWidget(dlg)
    assert dlg.save_button.isEnabled() is False
    assert dlg.up_button.isVisible() is False


def test_command_opens_and_enabled(tmp_path, qtbot):
    from vaultkeeper.ui.main_window import MainWindow

    ctrl = _controller(tmp_path, "aaa", "bbb")
    win = MainWindow(controller=ctrl)
    qtbot.addWidget(win)
    assert "MsHakPatchEditor" in win.implemented_commands()
    assert win.nit_menu.actions_by_id["MsHakPatchEditor"].isEnabled()
    win._on_command("MsHakPatchEditor")
    assert win._hak_patch_editor.isVisible()
