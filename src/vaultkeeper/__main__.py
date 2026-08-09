"""Vaultkeeper application entry point.

``python -m vaultkeeper`` launches the GUI. ``python -m vaultkeeper --scan``
prints the discovered NWN installs and resolved store layout (the headless probe,
useful for verifying the cross-platform path layer without a display).

The start-up recovery options (``-Settings``, ``-RestoreProfileData`` and the
rest, in :mod:`vaultkeeper.startup_options`) are read here too and passed on to
the GUI, which is where they take effect.
"""

from __future__ import annotations

import sys

from nwnfile.locations import discover_installs

from vaultkeeper import __version__
from vaultkeeper.app_paths import VaultStore, config_root


def _scan() -> int:
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


def _usage() -> int:
    from vaultkeeper.startup_options import usage_text

    print("Usage: vaultkeeper [option]...\n")
    print("  --scan   print the discovered NWN installs and store layout, then exit")
    print("  --help   show this message\n")
    print(usage_text())
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--scan" in args:
        return _scan()
    if "--help" in args or "-h" in args:
        return _usage()

    # Launch the GUI. Imported lazily so --scan works without a Qt display.
    from vaultkeeper.ui.app import run

    return run(argv=args)


if __name__ == "__main__":
    raise SystemExit(main())
