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
