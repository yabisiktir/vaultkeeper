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
    parser.add_argument("--states", action="store_true",
                        help="also cross-check per-mod install state vs files on disk "
                             "(catches ignored / hallucinated installs; scans the game)")
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

    state_findings: list = []
    if args.states and folders is not None:
        state_findings = _run_state_check(data_dir, args.game, args.user)

    all_findings = list(report.findings) + list(state_findings)
    if all_findings:
        shown = all_findings if args.list else all_findings[:15]
        print(f"\n{len(all_findings)} finding(s):")
        for f in shown:
            print(f"  [{f.kind}] {f.file_key}")
            print(f"      expected: {f.expected}  |  got: {f.actual}"
                  + (f"  ({f.detail})" if f.detail else ""))
        if not args.list and len(all_findings) > len(shown):
            print(f"  … {len(all_findings) - len(shown)} more (use --list)")
        return 1

    print("\nPASS — the port's install logic matches the original's recorded ledger"
          + (" and the on-disk state (no ignored / hallucinated installs)."
             if args.states else "."))
    return 0


def _run_state_check(data_dir: Path, game: Path | None, user: Path | None) -> list:
    """Open the live profile from its Profiles payloads and cross-check states vs disk."""
    from vaultkeeper.game.install_verify import verify_install_states
    from vaultkeeper.game.locations import discover_installs
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.session import default_game_user_path

    # data_dir is <store>/Data/<profile>; the payloads are <store>/Profiles/<profile>.
    profile = data_dir.name
    profile_mods = data_dir.parent.parent / "Profiles" / profile
    if not profile_mods.is_dir():
        print(f"\n(state check skipped — no payloads at {profile_mods})")
        return []
    if game is None:
        installs = discover_installs()
        if not installs:
            return []
        game = installs[0].root
    if user is None:
        user = default_game_user_path()
    print("\nScanning the game to cross-check install states (this can take ~15s)…")
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods, game_root=game, store_path=None, game_user_dir=user
    )
    checked, findings = verify_install_states(controller.pd, controller.ctx.game_folders)
    ignored = sum(1 for f in findings if f.kind == "ignored")
    halluc = sum(1 for f in findings if f.kind == "hallucination")
    print(f"  states: {checked} mods — ignored (on disk, says not installed): {ignored}; "
          f"hallucinated (says installed, not on disk): {halluc}")
    return findings


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
