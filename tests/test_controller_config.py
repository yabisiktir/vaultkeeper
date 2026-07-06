"""Tests for the controller's config-isolation drift check."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.install_manager import InstallContext
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, user_dir: Path) -> ProfileController:
    game_root = tmp_path / "NWN"
    mapper = Mapper(is_ee=True)
    ctx = InstallContext(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=game_root,
        game_folders=mapper.nwn_folder_paths(game_root),
        root_folder_name=game_root.name,
        mapper=mapper,
        game_user_dir=user_dir,
    )
    return ProfileController(ProfileData(), ctx)


def test_detects_game_config_drift(tmp_path, monkeypatch) -> None:
    # Point the snapshot at a temp config dir so the test is isolated.
    monkeypatch.setattr("vaultkeeper.ui.controller.config_root", lambda: tmp_path / "cfg")
    user_dir = tmp_path / "Documents" / "Neverwinter Nights"
    user_dir.mkdir(parents=True)
    (user_dir / "nwn.ini").write_text("[Display]\nWidth=1920\n")

    ctrl = _controller(tmp_path, user_dir)
    # First check: the ini appears as ADDED (no baseline yet).
    assert [c.kind.value for c in ctrl.game_config_changes()] == ["added"]
    # After accepting, in sync.
    ctrl.accept_game_config()
    assert ctrl.game_config_changes() == []
    # A change is detected, and the game file is never modified by the check.
    (user_dir / "nwn.ini").write_text("[Display]\nWidth=2560\n")
    changes = ctrl.game_config_changes()
    assert [c.kind.value for c in changes] == ["modified"]
    assert (user_dir / "nwn.ini").read_text() == "[Display]\nWidth=2560\n"


def test_no_guard_without_user_dir(tmp_path) -> None:
    game_root = tmp_path / "NWN"
    mapper = Mapper(is_ee=True)
    ctx = InstallContext(
        profile_mods_dir=tmp_path / "P",
        game_root=game_root,
        game_folders=mapper.nwn_folder_paths(game_root),
        root_folder_name=game_root.name,
        mapper=mapper,
        game_user_dir=None,
    )
    ctrl = ProfileController(ProfileData(), ctx)
    assert ctrl.game_config_changes() == []
