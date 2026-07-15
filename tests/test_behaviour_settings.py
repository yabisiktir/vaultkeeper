"""Finding-3 behaviour settings: uninstall-dependencies cascade + move-added-mods.

These wire real behaviour to the newly-added Settings toggles (VB
BehaviourUninstallDependencies / BehaviourMoveAddedMods).
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings, save_settings
from vaultkeeper.core import constants as C
from vaultkeeper.core.archive import FakeArchiveExtractor
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, **settings_kw) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    settings_path = tmp_path / "settings.json"
    save_settings(Settings(**settings_kw), settings_path)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        settings_path=settings_path,
    )


def test_uninstall_dependencies_cascade(tmp_path):
    ctrl = _controller(tmp_path)
    for name, deps in [("A", ["B"]), ("B", []), ("C", ["B"])]:
        md = ModData(group=C.GROUP_NONE, mod_name=name, mod_state=State.INSTALLED)
        md.dependencies.extend(deps)
        ctrl.pd.add_mod(md)

    # Uninstalling A alone keeps B — C still needs it.
    assert set(ctrl._with_removable_dependencies(["A"])) == {"A"}
    # Uninstalling A and C frees B (nothing installed still needs it).
    assert set(ctrl._with_removable_dependencies(["A", "C"])) == {"A", "B", "C"}


def test_move_added_mods_uses_default_group(tmp_path):
    ctrl = _controller(tmp_path, move_added_mods=True, default_group="Downloads")
    ctrl._extractor = FakeArchiveExtractor(contents={"cool.zip": {"hak/c.hak": b"C"}})
    archive = tmp_path / "cool.zip"
    archive.write_bytes(b"")

    result = ctrl.add_mods_from_files([archive])
    assert result["created"] == ["cool"]
    assert ctrl.pd.mod_item("cool").group == "Downloads"


def test_move_added_mods_off_leaves_ungrouped(tmp_path):
    ctrl = _controller(tmp_path, move_added_mods=False, default_group="Downloads")
    ctrl._extractor = FakeArchiveExtractor(contents={"cool.zip": {"hak/c.hak": b"C"}})
    archive = tmp_path / "cool.zip"
    archive.write_bytes(b"")

    ctrl.add_mods_from_files([archive])
    assert ctrl.pd.mod_item("cool").group == C.GROUP_NONE


def test_confirm_actions_off_skips_dialog(tmp_path, qtbot):
    """With confirm-actions off, _confirm proceeds without showing a dialog."""
    from vaultkeeper.ui.main_window import MainWindow

    ctrl = _controller(tmp_path, confirm_actions=False)
    win = MainWindow(controller=ctrl)
    qtbot.addWidget(win)
    # No QMessageBox is shown; the call returns True immediately.
    assert win._confirm("Delete", "Really?") is True
