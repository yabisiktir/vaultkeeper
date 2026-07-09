"""Session bootstrap — turn saved settings + game discovery into a live profile.

Launching the app should open the user's active profile if it can. This resolves
the NWN install (from settings, else auto-discovery) and the active profile's mod
directory + native store file, and builds a :class:`ProfileController`. If there
is not enough configured yet (no game located, or no profile chosen) it returns
``None`` and the window opens empty with guidance — the first-run/settings flow
(later) fills the gaps.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.game.locations import GameInstall, discover_installs
from vaultkeeper.ui.controller import ProfileController


def bootstrap_controller(
    settings: Settings | None = None,
    *,
    discover: Callable[[], list[GameInstall]] = discover_installs,
) -> ProfileController | None:
    """Open the active profile from settings/discovery, or ``None`` if unconfigured."""
    settings = settings or load_settings()
    store = settings.resolved_store()

    nwn_path = settings.nwn_path
    if not nwn_path:
        installs = discover()
        if installs:
            nwn_path = str(installs[0].root)

    if not nwn_path or not settings.active_profile:
        return None

    profile = settings.active_profile
    return ProfileController.open_profile(
        profile_mods_dir=store.profile_dir(profile),
        game_root=Path(nwn_path),
        store_path=store.data / f"{profile}.json",
        is_ee=True,
    )


def list_profiles(settings: Settings | None = None) -> list[str]:
    """Names of the profiles that exist in the store (Profiles subdirectories)."""
    settings = settings or load_settings()
    profiles_dir = settings.resolved_store().profiles
    if not profiles_dir.is_dir():
        return []
    return sorted(p.name for p in profiles_dir.iterdir() if p.is_dir())


def switch_profile(
    profile_name: str,
    *,
    settings: Settings | None = None,
    settings_path: Path | None = None,
) -> ProfileController | None:
    """Make ``profile_name`` the active profile and open it (persisting the choice)."""
    settings = settings or load_settings(settings_path)
    store = settings.resolved_store()
    store.profile_dir(profile_name).mkdir(parents=True, exist_ok=True)
    settings.active_profile = profile_name
    save_settings(settings, settings_path)
    return bootstrap_controller(settings)


def list_legacy_profiles(legacy_store_root: str | Path) -> list[str]:
    """Profile names found in a legacy NIT Store (its ``Data\\`` subfolders)."""
    from vaultkeeper.persistence.nrbf.migrate import list_profiles as _legacy_profiles

    return _legacy_profiles(Path(legacy_store_root))


def import_legacy_profile(
    legacy_store_root: str | Path,
    profile_name: str,
    *,
    settings: Settings | None = None,
    settings_path: Path | None = None,
    make_active: bool = False,
) -> Path:
    """Migrate a legacy NIT Store profile into the native store; return its JSON path.

    Reads the legacy profile's ModData (NRBF) into a native ``ProfileData`` and writes
    it to the native store's ``Data/<profile>.json``, creating the profile's mods
    directory. The file/install tables rebuild from disk when the profile is opened.
    When ``make_active`` is set, the profile is recorded as active in settings.
    """
    from vaultkeeper.persistence.nrbf.migrate import migrate_profile
    from vaultkeeper.persistence.profile_store import save_profile

    settings = settings or load_settings(settings_path)
    store = settings.resolved_store()
    store.ensure()
    store.profile_dir(profile_name).mkdir(parents=True, exist_ok=True)

    pd = migrate_profile(Path(legacy_store_root), profile_name)
    target = store.data / f"{profile_name}.json"
    save_profile(pd, target)

    if make_active:
        settings.active_profile = profile_name
        save_settings(settings, settings_path)
    return target


def configure_profile(
    nwn_path: str,
    profile_name: str,
    *,
    settings: Settings | None = None,
    settings_path: Path | None = None,
) -> ProfileController:
    """Persist a game path + profile choice, create the store tree, and open it.

    Used by the first-run / "Set Up Profile" flow: records the selection in the
    isolated settings file (never in the game folder), ensures the store and the
    profile's mods directory exist, then returns a live controller.
    """
    settings = settings or load_settings(settings_path)
    settings.nwn_path = nwn_path
    settings.active_profile = profile_name

    store = settings.resolved_store()
    store.ensure()
    store.profile_dir(profile_name).mkdir(parents=True, exist_ok=True)
    save_settings(settings, settings_path)

    controller = bootstrap_controller(settings, discover=lambda: [])
    if controller is None:  # pragma: no cover - guaranteed configured above
        raise RuntimeError("profile configuration did not yield a controller")
    return controller
