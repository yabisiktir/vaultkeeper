"""Vaultkeeper application entry point.

Phase 0 stub: the GUI (PySide6 main window) arrives in Phase 3. For now this
provides a runnable ``vaultkeeper`` command that reports discovered NWN installs
and the resolved store layout — useful for verifying the cross-platform path
layer on a real machine without any UI.
"""

from __future__ import annotations

import sys

from vaultkeeper import __version__
from vaultkeeper.app_paths import VaultStore, config_root
from vaultkeeper.game.locations import discover_installs


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    print(f"Vaultkeeper {__version__}")
    print(f"Config:   {config_root()}")
    store = VaultStore.default()
    print(f"Store:    {store.root}" + ("  (network)" if store.is_network() else ""))

    installs = discover_installs()
    if not installs:
        print("\nNo Neverwinter Nights installations found automatically.")
        print("You will be able to locate one manually in the app.")
        return 0

    print(f"\nFound {len(installs)} NWN install candidate(s):")
    for install in installs:
        tags = [install.kind.value, install.edition.value]
        if install.is_wine:
            tags.append(f"wine:{install.wine_prefix}")
        if install.is_network:
            tags.append("network")
        print(f"  - {install.root}  [{', '.join(tags)}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
