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

from enum import IntEnum


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
