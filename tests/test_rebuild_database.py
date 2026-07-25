"""Regression tests for Rebuild Database — must never discard imported mods/groups.

Bug (2026-07-25): pressing Rebuild Database on a mixed/imported profile wiped every
mod without an on-disk installer folder plus all custom groups, because the rebuild
did a fresh ``scan_mods`` (which rebuilds purely from disk). Fixed to preserve
definitions + groups when any mod has no folder.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Data" / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "Data" / "P.json",
    )


def _add_imported_mod(controller: ProfileController, name: str, group: str) -> None:
    """Add a mod that exists only as a definition + file keys (no on-disk folder)."""
    controller.pd.mod_list.setdefault(group, ModData(group=group))  # the group row
    md = ModData(group=group, mod_name=name)
    md.files.append(FileKeyInfo(group, name, "hak", f"{name}.hak"))
    controller.pd.mod_list[name] = md
    controller.pd.initialise_groups()


def test_rebuild_preserves_imported_mods_and_groups(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    # One real on-disk mod…
    controller.create_mod("OnDisk Mod")
    payload = (
        tmp_path / "Data" / "Profiles" / "P" / "OnDisk Mod" / C.MOD_INSTALLER_DIR
        / "override" / "a.2da"
    )
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"DATA")
    controller.build_installer_payload("OnDisk Mod")
    # …and several imported-only mods in custom groups (the shape that was wiped).
    _add_imported_mod(controller, "Imported Alpha", "100.  Community Packs")
    _add_imported_mod(controller, "Imported Beta", "100.  Community Packs")
    _add_imported_mod(controller, "Imported Gamma", "800.  Worth Playing")
    controller.save()

    before = set(controller.pd.mod_keys)
    groups_before = set(controller.pd.group_keys)
    assert "Imported Alpha" in before and "100.  Community Packs" in groups_before

    controller.rebuild_database()

    after = set(controller.pd.mod_keys)
    # Nothing lost: the on-disk mod AND every imported mod survive.
    assert before <= after, f"lost mods: {before - after}"
    assert {"Imported Alpha", "Imported Beta", "Imported Gamma", "OnDisk Mod"} <= after
    # Custom groups survive too.
    assert {"100.  Community Packs", "800.  Worth Playing"} <= set(controller.pd.group_keys)


def test_rebuild_backs_up_the_store_first(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.create_mod("A")
    controller.save()

    controller.rebuild_database()

    backups = tmp_path / "Data" / "Backups"
    assert backups.is_dir()
    copies = list(backups.glob("P (pre-rebuild*.json"))
    assert copies, "expected a pre-rebuild backup of the profile store"


def test_rebuild_pure_native_profile_still_rescans(tmp_path: Path) -> None:
    # A profile where every mod has an on-disk folder: the full rescan path is safe.
    controller = _controller(tmp_path)
    for name in ("Mod One", "Mod Two"):
        controller.create_mod(name)
        payload = (
            tmp_path / "Data" / "Profiles" / "P" / name / C.MOD_INSTALLER_DIR
            / "override" / f"{name}.2da"
        )
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(b"X")
        controller.build_installer_payload(name)
    controller.save()

    controller.rebuild_database()
    assert {"Mod One", "Mod Two"} <= set(controller.pd.mod_keys)
