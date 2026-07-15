"""CLI — verify the port's install logic against the original tool's recorded ledger.

The original NWN Installer Tool records what it installed in ``nit.InstallData_*`` /
``nit.FileData_*`` per profile. This compares that authoritative record against what
the port's engine computes — conflict winners, placement, on-disk presence, and (when
the original recorded CRCs) content — so install correctness can be checked without
running the original or re-installing anything.

Usage::

    python -m vaultkeeper.verify_install                 # auto-detect store + game
    python -m vaultkeeper.verify_install "<profile data dir>"
    python -m vaultkeeper.verify_install "<dir>" --game "<nwn root>" --user "<user dir>"
    python -m vaultkeeper.verify_install --list          # list findings in full

Exit code is 0 on a full match, 1 if any parity finding is reported.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vaultkeeper.core.mapper import Mapper
from vaultkeeper.game.install_verify import load_ledger, verify_ledger
from vaultkeeper.game.nwn_folders import read_alias_locations


def _default_profile_data_dir() -> Path | None:
    """The first profile inside a detected legacy NIT Store, if any."""
    from vaultkeeper.ui.session import detect_legacy_store, list_legacy_profiles

    store = detect_legacy_store()
    if store is None:
        return None
    profiles = list_legacy_profiles(store)
    if not profiles:
        return None
    return store / "Data" / profiles[0]


def _resolve_game_folders(game: Path | None, user: Path | None) -> dict[str, Path] | None:
    """Resolve {folder: path} for the live checks from args or auto-discovery."""
    from vaultkeeper.game.locations import discover_installs
    from vaultkeeper.ui.session import default_game_user_path

    if game is None:
        installs = discover_installs()
        if not installs:
            return None
        game = installs[0].root
    if user is None:
        user = default_game_user_path()
    alias = read_alias_locations(user) if user else None
    return Mapper(is_ee=True).nwn_folder_paths(game, user_dir=user, alias_locations=alias)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profile_data_dir", nargs="?", type=Path,
                        help="a legacy store's Data/<profile> directory (auto-detected if omitted)")
    parser.add_argument("--game", type=Path, help="NWN install root (else auto-discovered)")
    parser.add_argument("--user", type=Path, help="NWN user folder (else the platform default)")
    parser.add_argument("--offline", action="store_true", help="skip the live on-disk checks")
    parser.add_argument("--list", action="store_true", help="print every finding, not just counts")
    args = parser.parse_args(argv)

    data_dir = args.profile_data_dir or _default_profile_data_dir()
    if data_dir is None or not data_dir.is_dir():
        print("No profile data directory found. Pass one explicitly, e.g.:")
        print('  python -m vaultkeeper.verify_install "~/Documents/NIT Store/Data/<profile>"')
        return 2
    print(f"Ledger: {data_dir}")

    ledger = load_ledger(data_dir)
    if not ledger.installed:
        print("No install ledger (nit.InstallData_*) in that directory.")
        return 2

    folders = None if args.offline else _resolve_game_folders(args.game, args.user)
    if folders is None and not args.offline:
        print("(no game install found — running offline checks only)")

    report = verify_ledger(ledger, game_folders=folders)
    print(report.summary())

    if report.findings:
        shown = report.findings if args.list else report.findings[:15]
        print(f"\n{len(report.findings)} finding(s):")
        for f in shown:
            print(f"  [{f.kind}] {f.file_key}")
            print(f"      original: {f.expected}  |  port: {f.actual}"
                  + (f"  ({f.detail})" if f.detail else ""))
        if not args.list and len(report.findings) > len(shown):
            print(f"  … {len(report.findings) - len(shown)} more (use --list)")
        return 1

    print("\nPASS — the port's install logic matches the original's recorded ledger.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
