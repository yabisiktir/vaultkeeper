"""Install-state and rating enums (data-contract integer values).

Ported from ``ProfileData.Defs.vb`` (``Pde.State``, ``Pde.Ratings``). The integer
values are persisted, so they must match the VB source exactly.

State ordering encodes meaning: ``NotInstalled`` (1) is the "installed?" boundary
at the file level (``FileData.Installed`` = ``FileState > NotInstalled``), while
``InstallState`` (10) is the mod-level threshold (values >= it are "installed").
The gap (2–4) holds the partial mod states; the >=11 band holds file/mod
installed variants. ``None`` (-2) means "no installer exists for this mod".
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class State(IntEnum):
    """Installation status of a file or a mod (Pde.State)."""

    NONE = -2               # no Mod Installer has been created for this mod
    UNKNOWN = 0             # install state not yet determined
    NOT_INSTALLED = 1       # not installed by the user
    SOME_INSTALLED = 2      # some (not all) files installed
    SOME_AND_MATCH = 3      # some installed; the installed ones match
    SOME_AND_OVERRIDDEN = 4  # some installed; overridden ones are the same
    INSTALL_STATE = 10      # threshold sentinel: >= is "installed" (never stored)
    INSTALLED = 11          # installed by the user / file installed
    MATCH_OVERRIDE = 12     # overridden by another mod, but files are identical
    INSTALLED_AND_OVERRIDDEN = 13  # some installed, some overridden
    OVERRIDDEN = 14         # overridden by another mod

    def describe(self, *, of_file: bool = False) -> str:
        """What this state means, in words (VB ``statusicons.htm``).

        The original shows these in the Mod Properties and Details panels; the
        port was showing the enum name title-cased, so a mod sat there saying
        "Some And Overridden", which is a label rather than an explanation.

        Mods and files differ in wording where the same state means a slightly
        different thing about each — a file is overridden by *a* file, a mod by
        the files of other mods.
        """
        return (_FILE_DESCRIPTIONS if of_file else _MOD_DESCRIPTIONS).get(
            self, self.name.replace("_", " ").title()
        )

    @property
    def is_file_installed(self) -> bool:
        """File-level "installed?" test (FileData.Installed = state > NotInstalled)."""
        return self > State.NOT_INSTALLED

    @property
    def is_mod_installed(self) -> bool:
        """Mod-level "installed?" test (state >= InstallState)."""
        return self >= State.INSTALL_STATE


class Ratings(IntEnum):
    """User mod ratings (Pde.Ratings), values verified against ProfileData.Defs.vb."""

    NONE = 0
    EXCELLENT = 1
    GOOD = 2
    MEDIUM = 3
    MEDIOCRE = 4
    BAD = 5
    HORRIBLE = 6
    ABANDONED = 7


class Weapon(IntEnum):
    """Best-weapon mod property (Pde.Weapon). Values verified against source.

    Standard weapons are 0..36; custom weapons jump to 1000+ (persisted values).
    """

    NONE = 0
    BASTARD_SWORD = 1
    GREAT_SWORD = 2
    KATANA = 3
    LONG_SWORD = 4
    RAPIER = 5
    SCIMITAR = 6
    SHORT_SWORD = 7
    DAGGER = 8
    KUKRI = 9
    TWOBLADED_SWORD = 10
    DOUBLE_AXE = 11
    GREATAXE = 12
    BATTLEAXE = 13
    HANDAXE = 14
    MORNINGSTAR = 15
    HEAVY_FLAIL = 16
    LIGHT_FLAIL = 17
    DIRE_MACE = 18
    MACE = 19
    WARHAMMER = 20
    LIGHT_HAMMER = 21
    SCYTHE = 22
    HALBERD = 23
    SPEAR = 24
    TRIDENT = 25
    CLUB = 26
    QUARTERSTAFF = 27
    MAGIC_STAFF = 28
    SICKLE = 29
    KAMA = 30
    WHIP = 31
    HEAVY_CROSSBOW = 32
    LIGHT_CROSSBOW = 33
    LONGBOW = 34
    SHORTBOW = 35
    SLING = 36
    # Custom weapons
    FALCHION = 1000
    MOON_ON_A_STICK = 1001
    DWARVEN_WARAXE = 1002
    LANCE = 1003
    SAI = 1004
    NUNCHAKU = 1005
    KATAR = 1006
    MAUL = 1007
    MERCURIAL_LONGSWORD = 1008
    MERCURIAL_GREATSWORD = 1009
    SCIMITAR_DOUBLE = 1010
    WIND_FIREWHEEL = 1011
    MAUG_DOUBLESWORD = 1012
    SHORT_SPEAR = 1013


class GroupStatus(StrEnum):
    """Expanded/collapsed state of a group row (LazWorks FileViewGroupStatus).

    Serialized by name in Vaultkeeper's native store (VB integer values are only
    relevant to the deferred legacy NRBF importer).
    """

    EXPANDED = "expanded"
    COLLAPSED = "collapsed"


#: What each state means for a **mod**, from ``statusicons.htm``.
_MOD_DESCRIPTIONS: dict[State, str] = {
    State.NONE: "This mod does not have a Mod Installer.",
    State.UNKNOWN: "This mod's install state has not been worked out yet.",
    State.NOT_INSTALLED: "This mod is not installed.",
    State.SOME_INSTALLED: (
        "This mod is not installed, but some of its files already exist in the "
        "Neverwinter Nights installation or User Files folders."
    ),
    State.SOME_AND_MATCH: (
        "This mod is not installed, but some of its files already exist in the "
        "Neverwinter Nights installation or User Files folders and would be "
        "overridden by another mod's identical files."
    ),
    State.SOME_AND_OVERRIDDEN: (
        "This mod is not installed, but some of its files already exist in the "
        "Neverwinter Nights installation or User Files folders and would be "
        "overridden by another mod's files."
    ),
    State.INSTALLED: "This mod is installed.",
    State.MATCH_OVERRIDE: (
        "Some or all of this mod's files have been overridden by other mods, "
        "but the files are identical."
    ),
    State.INSTALLED_AND_OVERRIDDEN: (
        "Some, but not all, of this mod's files have been overridden by other mods."
    ),
    State.OVERRIDDEN: "All of this mod's files have been overridden by other mods.",
}

#: The same, for a single **file**.
_FILE_DESCRIPTIONS: dict[State, str] = {
    State.NONE: "This file belongs to no Mod Installer.",
    State.UNKNOWN: "This file's install state has not been worked out yet.",
    State.NOT_INSTALLED: "This file is not installed.",
    State.INSTALLED: "This file is installed.",
    State.MATCH_OVERRIDE: (
        "This file has been overridden by another mod's file, but the files are "
        "identical."
    ),
    State.OVERRIDDEN: "This file has been overridden by another mod's file.",
}
