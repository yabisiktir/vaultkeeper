"""Tests for group organisation (move to group, rename group, mandatory groups)."""

from __future__ import annotations

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import State


def _pd_with_mods(*names: str) -> ProfileData:
    pd = ProfileData()
    for name in names:
        md = ModData(group=C.GROUP_NONE, mod_name=name)
        fk = FileKeyInfo(C.GROUP_NONE, name, "hak", f"{name}.hak")
        md.files.append(fk)
        pd.mod_list[name] = md
        from vaultkeeper.core.file_data import FileData

        pd.file_list[fk] = FileData(key=fk, file_state=State.NOT_INSTALLED)
    pd.ensure_mandatory_groups()
    return pd


def test_mandatory_groups_created() -> None:
    pd = ProfileData()
    pd.ensure_mandatory_groups()
    assert C.GROUP_NONE in pd.groups
    assert C.GROUP_INSTALLED in pd.groups


def test_move_to_new_group_rewrites_keys() -> None:
    pd = _pd_with_mods("Alpha", "Beta")
    pd.move_mods_to_group(["Alpha"], "Adventures")

    md = pd.mod_item("Alpha")
    assert md.group == "Adventures"
    # File keys were rewritten to carry the new group.
    assert all(fk.group == "Adventures" for fk in md.files)
    assert all(fk in pd.file_list for fk in md.files)
    # The new group row + view exist.
    assert "Adventures" in pd.groups
    assert pd.groups["Adventures"].member_names == ["Alpha"]
    # Beta stayed put.
    assert pd.mod_item("Beta").group == C.GROUP_NONE


def test_rename_group_moves_members() -> None:
    pd = _pd_with_mods("Alpha")
    pd.move_mods_to_group(["Alpha"], "Old Group")
    assert pd.rename_group("Old Group", "New Group")

    assert "Old Group" not in pd.groups
    assert "New Group" in pd.groups
    assert pd.mod_item("Alpha").group == "New Group"
    assert pd.groups["New Group"].member_names == ["Alpha"]


def test_rename_group_guards() -> None:
    pd = _pd_with_mods("Alpha")
    pd.move_mods_to_group(["Alpha"], "G1")
    # Cannot rename a reserved group, a missing group, or onto an existing name.
    assert not pd.rename_group(C.GROUP_NONE, "Whatever")
    assert not pd.rename_group("Nope", "X")
    pd.move_mods_to_group(["Alpha"], "G2")
    assert not pd.rename_group("G1", "G2")  # G1 now empty group row still exists
