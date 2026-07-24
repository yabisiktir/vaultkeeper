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


def test_controller_groups_includes_empty_groups(tmp_path) -> None:
    """Empty groups must still render as drag-drop targets.

    VB ApplyGroupsAndStatus (NIT.ModView.vb) adds a header for every pd.Groups
    row before placing any mods, so an empty group is still shown.
    """
    from vaultkeeper.persistence.profile_store import save_profile
    from vaultkeeper.ui.controller import ProfileController

    pd = ProfileData()
    pd.add_mod(ModData(group="Alpha", mod_name="A"))
    pd.ensure_mandatory_groups()
    pd.move_mods_to_group([], "Empty Group")  # a group row with no members
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)

    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )
    grouped = dict(controller.groups())
    assert "Alpha" in grouped
    assert "Empty Group" in grouped  # the fix — was dropped before
    assert grouped["Empty Group"] == []


def test_rename_group_guards() -> None:
    pd = _pd_with_mods("Alpha")
    pd.move_mods_to_group(["Alpha"], "G1")
    # Cannot rename a reserved group, a missing group, or onto an existing name.
    assert not pd.rename_group(C.GROUP_NONE, "Whatever")
    assert not pd.rename_group("Nope", "X")
    pd.move_mods_to_group(["Alpha"], "G2")
    assert not pd.rename_group("G1", "G2")  # G1 now empty group row still exists


def test_remove_group_only_empty_and_non_mandatory() -> None:
    pd = _pd_with_mods("Alpha")
    pd.move_mods_to_group(["Alpha"], "G1")  # G1 row + member Alpha
    assert not pd.remove_group("G1")  # still has a member
    assert not pd.remove_group(C.GROUP_NONE)  # mandatory
    assert not pd.remove_group("Missing")  # no such group
    pd.move_mods_to_group(["Alpha"], "G2")  # G1 now empty
    assert pd.remove_group("G1")  # empty, non-mandatory → removed
    assert "G1" not in pd.mod_list
    assert not pd.remove_group("G1")  # already gone


def test_delete_groups_removes_members_row_and_persists(tmp_path) -> None:
    from vaultkeeper.persistence.profile_store import load_profile, save_profile
    from vaultkeeper.ui.controller import ProfileController

    pd = ProfileData()
    pd.add_mod(ModData(group="Adventures", mod_name="A"))
    pd.add_mod(ModData(group="Adventures", mod_name="B"))
    pd.add_mod(ModData(group="Campaigns", mod_name="C"))
    pd.add_mod(ModData(group="Adventures"))  # explicit group row
    pd.initialise_groups()
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    controller = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
        game_user_dir=tmp_path / "user",
    )

    assert set(controller.group_member_names("Adventures")) == {"A", "B"}
    report = controller.delete_groups(["Adventures"])
    assert report["deleted_mods"] == 2
    assert report["removed_groups"] == ["Adventures"]
    assert report["failed_groups"] == []
    assert controller.pd.mod_keys == ["C"]
    assert "Adventures" not in controller.group_names()

    # Persisted to disk.
    reloaded = load_profile(store)
    assert reloaded.mod_keys == ["C"]
    assert "Adventures" not in [
        m.group for m in reloaded.mod_list.values() if m.is_group_item
    ]
