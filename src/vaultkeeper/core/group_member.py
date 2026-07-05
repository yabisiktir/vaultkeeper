"""GroupMemberData — a live view of the mods belonging to a group.

Ported from ``GroupMemberData.vb``. This holds only a group name; every other
property is derived by querying the profile's ``ModList``. So it is a thin view
over the mod dictionary rather than a stored record. Here it takes the mod dict
directly, which keeps it testable without a full ProfileData.

The mutating operations (``rename``, ``add_members``, ``remove``) rewrite group
membership + file keys across the whole profile graph and recompute states; they
land with ProfileData (VB refs retained in comments) and are not part of this
view.
"""

from __future__ import annotations

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import GroupStatus

# The profile's ModList: name -> ModData (mods and group rows).
ModList = dict[str, ModData]


class GroupMemberData:
    """View of one group's member mods within a ModList."""

    def __init__(self, group_name: str, mod_list: ModList) -> None:
        self.group_name = group_name
        self._mod_list = mod_list

    def _member_items(self) -> list[tuple[str, ModData]]:
        return [
            (name, md)
            for name, md in self._mod_list.items()
            if md.is_not_group_item and md.group == self.group_name
        ]

    @property
    def state(self) -> GroupStatus:
        """The group row's expanded/collapsed state."""
        return self._mod_list[self.group_name].group_state

    @property
    def members(self) -> list[ModData]:
        return [md for _, md in self._member_items()]

    @property
    def member_names(self) -> list[str]:
        return [name for name, _ in self._member_items()]

    @property
    def count(self) -> int:
        return len(self._member_items())

    @property
    def installed_members(self) -> list[ModData]:
        return [md for md in self.members if md.installed]

    @property
    def installed_count(self) -> int:
        return sum(1 for md in self.members if md.installed)
