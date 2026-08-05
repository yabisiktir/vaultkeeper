"""Where the optional real-data tests look for real data.

A handful of tests check the code against genuine artefacts rather than fixtures —
a legacy NIT Store to import, a real NWN install to resolve folders against, a
Steam Workshop folder. They are worth having: a fixture cannot tell you that an
import of somebody's actual ten-year-old store still resolves on disk.

**Nothing depends on any of it.** Every path here is opt-in through an environment
variable and every test that uses one skips when it is unset or missing, so the
suite is complete and green on a machine that has none of them — which is every CI
runner, and anyone who is not the author.

These used to be hardcoded absolute paths under one person's home directory. That
put someone's private folder layout in a public-facing repository, and it made the
tests lie: a mark guarding one of them sat on a helper rather than the test, so it
ran on all three CI platforms and failed there, asserting about a store that could
not possibly exist on a runner.

To run them, point at your own:

    export VAULTKEEPER_TEST_NIT_STORE="$HOME/Documents/NIT Store"
    export VAULTKEEPER_TEST_NWN_USER_DIR="$HOME/Documents/Neverwinter Nights"
    export VAULTKEEPER_TEST_NWN_INSTALL="/path/to/Neverwinter Nights"
    export VAULTKEEPER_TEST_STEAM_WORKSHOP="/path/to/workshop/content/704450"
"""

from __future__ import annotations

import os
from pathlib import Path

#: The environment variable naming each optional folder.
NIT_STORE_VAR = "VAULTKEEPER_TEST_NIT_STORE"
USER_DIR_VAR = "VAULTKEEPER_TEST_NWN_USER_DIR"
INSTALL_VAR = "VAULTKEEPER_TEST_NWN_INSTALL"
WORKSHOP_VAR = "VAULTKEEPER_TEST_STEAM_WORKSHOP"


def _folder(variable: str) -> Path | None:
    """The folder ``variable`` names, if it is set and actually there."""
    value = os.environ.get(variable, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_dir() else None


def nit_store() -> Path | None:
    """A legacy NIT Store to import from, or ``None``."""
    return _folder(NIT_STORE_VAR)


def nwn_user_dir() -> Path | None:
    """A real NWN user directory (saves, hak, portraits), or ``None``."""
    return _folder(USER_DIR_VAR)


def nwn_install() -> Path | None:
    """A real NWN installation, or ``None``."""
    return _folder(INSTALL_VAR)


def steam_workshop() -> Path | None:
    """A real Steam Workshop content folder for NWN, or ``None``."""
    return _folder(WORKSHOP_VAR)


def missing(*folders: Path | None) -> bool:
    """Whether any of these is absent — the usual ``skipif`` condition."""
    return any(folder is None for folder in folders)


#: Said once, so every skip reads the same and explains how to opt in.
REASON = (
    "needs real data; set VAULTKEEPER_TEST_NIT_STORE / _NWN_USER_DIR / "
    "_NWN_INSTALL / _STEAM_WORKSHOP to run it (see tests/real_data.py)"
)
