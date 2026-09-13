"""The one-click 'Recognise Installed + Rebuild Dependencies' convenience.

Chains the two steps someone reaches for after installing mods outside
Vaultkeeper: recognise what is installed in the game folder
(``rescan_installed_state``), then rebuild the dependency mapping via the shared
Auto flow. Declining the rebuild still leaves the recognition done.
"""

from __future__ import annotations

from pathlib import Path

import vaultkeeper.ui.dialogs.dependency_manager as dm
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def _window(qtbot, tmp_path: Path) -> MainWindow:
    pd = ProfileData()
    pd.add_mod(ModData(group="G", mod_name="A"))
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )
    win = MainWindow(controller=controller)
    qtbot.addWidget(win)
    return win


def test_menu_item_present_and_enabled(qtbot, tmp_path: Path) -> None:
    win = _window(qtbot, tmp_path)
    action = win.nit_menu.action("MsRecogniseRebuildDeps")
    assert action is not None
    assert action.isEnabled()  # a real handler exists, so it is not greyed out


def test_chains_recognise_then_rebuild(qtbot, tmp_path: Path, monkeypatch) -> None:
    win = _window(qtbot, tmp_path)
    calls: list[str] = []

    def fake_rescan() -> str:
        calls.append("rescan")
        return "Rescan complete: 2 of 5 mods installed."

    def fake_auto(controller, parent) -> dict:
        calls.append("auto")
        return {"message": "Checked 3 mod(s) with a project link. Updated 1.", "updated": 1}

    monkeypatch.setattr(win.controller, "rescan_installed_state", fake_rescan)
    monkeypatch.setattr(dm, "run_auto_dependencies", fake_auto)

    win._on_recognise_and_rebuild_dependencies()

    assert calls == ["rescan", "auto"]  # recognise first, then rebuild
    status = win.nit_status.mg_info.text()
    assert "Rescan complete" in status
    assert "Checked 3" in status


def test_declining_rebuild_still_recognises(qtbot, tmp_path: Path, monkeypatch) -> None:
    win = _window(qtbot, tmp_path)
    monkeypatch.setattr(
        win.controller, "rescan_installed_state", lambda: "Rescan complete: 1 of 1 mods installed."
    )
    # run_auto_dependencies returns None when the user declines the confirm.
    monkeypatch.setattr(dm, "run_auto_dependencies", lambda controller, parent: None)

    win._on_recognise_and_rebuild_dependencies()

    status = win.nit_status.mg_info.text()
    assert "Rescan complete" in status
    assert "skipped" in status.lower()
