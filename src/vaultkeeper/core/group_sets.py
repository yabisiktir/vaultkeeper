"""The starting sets of group names offered for a new profile (VB ``GroupSets``).

A group set is only a **starting point** — every name here can be renamed,
removed or added to afterwards. What it is really deciding is the *numbering*,
and that is not cosmetic: groups sort by name, the sort order is the order mod
files are copied, and that order is what settles a file conflict between two
mods. Picking a set is picking a conflict policy, which is why the tool asks
rather than assuming.

The first entry is the default. "None" is a real answer, not a way out of the
question.
"""

from __future__ import annotations

from vaultkeeper.core import constants as C

#: Set name → its group names, in order. VB ``ProfileData.Config.GroupSets``.
GROUP_SETS: dict[str, list[str]] = {
    "Groups are based on category and usage (eg Worth Playing, Evaluating, etc)": [
        C.RESTORER_GROUP,
        C.CHARACTER_RESTORER_GROUP,
        "100.  Community Packs",
        "110.  Utility Mods",
        "120.  UI, Texture and Music",
        "130.  Portrait Packs",
        "140.  Common Resources",
        "200.  Not worth playing",
        "210.  Unlikely to play",
        "220.  Might try one day",
        "300.  New Mods",
        "700.  Borderline Worth Playing",
        "800.  Worth Playing",
        C.DEFAULT_GROUP,
        "900.  Patches",
        "990.  Install Last",
    ],
    "Groups are based on a smaller number of usage scenarios (eg New Mods, etc)": [
        C.RESTORER_GROUP,
        C.CHARACTER_RESTORER_GROUP,
        "100.  Community Packs",
        "110.  Utility Mods",
        "200.  Not worth playing",
        "210.  Unlikely to play",
        "220.  Played but not rated",
        "230.  Might try one day",
        "300.  New Mods",
        "800.  Worth Playing",
        C.DEFAULT_GROUP,
        "900.  Install Last",
    ],
    "Groups are based on Nexus Mods categories": [
        C.RESTORER_GROUP,
        "010.  Community Packs",
        "020.  Armour and Clothing",
        "030.  Characters",
        "040.  Creatures",
        "050.  Hakpaks",
        "060.  Miscellaneous",
        "070.  Models",
        "080.  Portraits",
        "090.  Prefabs",
        "100.  Scripts",
        "110.  Sounds",
        "120.  Textures",
        "130.  User Interface",
        "140.  Utilities",
        "150.  Videos and trailers",
        "160.  Weapons",
        "800.  Modules",
        "805.  Persistent Worlds ",
        C.DEFAULT_GROUP,
        "950.  Install Last",
    ],
    "None (no pre-defined Groups)": [],
}

#: The set used when nobody is asked (VB takes the first entry as the default).
DEFAULT_SET_NAME = next(iter(GROUP_SETS))


def group_names(set_name: str) -> list[str]:
    """The groups in a set; the default set's when the name is not one of ours."""
    return list(GROUP_SETS.get(set_name, GROUP_SETS[DEFAULT_SET_NAME]))


def set_names() -> list[str]:
    """The set names, default first."""
    return list(GROUP_SETS)
