"""Tests for GroupMemberData (a view over ModList)."""

from __future__ import annotations

from vaultkeeper.core.group_member import GroupMemberData
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import GroupStatus, State


def _build() -> dict[str, ModData]:
    mods: dict[str, ModData] = {}
    # Group rows
    grp = ModData(group="Adventures")
    grp.group_state = GroupStatus.COLLAPSED
    mods["Adventures"] = grp
    mods["Other"] = ModData(group="Other")
    # Members of "Adventures"
    a = ModData(group="Adventures", mod_name="Alpha")
    a.mod_state = State.INSTALLED
    b = ModData(group="Adventures", mod_name="Beta")
    b.mod_state = State.NOT_INSTALLED
    # Member of a different group
    c = ModData(group="Other", mod_name="Gamma")
    mods["Alpha"] = a
    mods["Beta"] = b
    mods["Gamma"] = c
    return mods


def test_members_and_count() -> None:
    gmd = GroupMemberData("Adventures", _build())
    assert gmd.count == 2
    assert set(gmd.member_names) == {"Alpha", "Beta"}


def test_excludes_group_rows_and_other_groups() -> None:
    gmd = GroupMemberData("Adventures", _build())
    names = gmd.member_names
    assert "Adventures" not in names  # group row itself excluded
    assert "Gamma" not in names       # belongs to another group


def test_installed_members() -> None:
    gmd = GroupMemberData("Adventures", _build())
    assert gmd.installed_count == 1
    assert [m.mod_name for m in gmd.installed_members] == ["Alpha"]


def test_state_reads_group_row() -> None:
    gmd = GroupMemberData("Adventures", _build())
    assert gmd.state == GroupStatus.COLLAPSED


def test_empty_group() -> None:
    gmd = GroupMemberData("Other", _build())
    assert gmd.count == 1  # Gamma
    assert gmd.installed_count == 0
