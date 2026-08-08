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

from nwnfile.editions import Edition
from nwnfile.locations import GameInstall, discover_installs

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.ui.controller import ProfileController

#: Default profile names created on first run (VB ``Paths.DefaultProfile`` /
#: ``Paths.DefaultEeProfile``), chosen by the detected game edition.
DEFAULT_PROFILE = "Neverwinter Nights Mods"
DEFAULT_EE_PROFILE = "Enhanced Edition Mods"


def default_profile_name(edition: Edition) -> str:
    """The first-run default profile name for a game edition (VB Paths defaults)."""
    return DEFAULT_EE_PROFILE if edition == Edition.ENHANCED else DEFAULT_PROFILE


def auto_configure_first_run(
    settings: Settings | None = None,
    *,
    choices=None,
    settings_path: Path | None = None,
    discover: Callable[[], list[GameInstall]] = discover_installs,
) -> ProfileController | None:
    """Establish a default profile on first run from the discovered install.

    Faithful to the VB startup (``Paths.vb`` ~1615-1643): when no profile is active
    yet, the tool auto-creates a default profile named for the detected edition
    (``Enhanced Edition Mods`` / ``Neverwinter Nights Mods``) against the discovered
    game folder — the user is never dropped into an empty, profile-less state. When
    nothing is discovered (VB solicits paths) this returns ``None`` so the caller
    falls back to the manual *Set Up Profile* flow. A no-op when a profile is already
    active.

    ``choices`` carries whatever the first-run screen settled — which installation,
    and which drive the store goes on. Without it the first discovered install and
    the platform default are used, which is what this did before that screen
    existed and remains the behaviour when there was nothing worth asking.
    """
    settings = settings or load_settings(settings_path)
    if settings.active_profile:
        return None
    installs = discover()
    chosen_root = getattr(choices, "game_root", "") or ""
    if not installs and not chosen_root:
        return None

    install = next(
        (i for i in installs if str(i.root) == chosen_root),
        installs[0] if installs else None,
    )
    edition = install.edition if install is not None else Edition.ENHANCED
    return configure_profile(
        chosen_root or str(install.root),
        default_profile_name(edition),
        store_root=getattr(choices, "store_root", "") or None,
        settings=settings,
        settings_path=settings_path,
    )


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
        map_overrides=settings.map_overrides or None,
        map_exclude_overrides=settings.map_exclude_overrides or None,
        settings_path=store.settings_file,
        game_user_dir=Path(settings.game_user_path) if settings.game_user_path else None,
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


def detect_legacy_store() -> Path | None:
    """Best-guess location of an existing legacy NIT Store, or ``None``.

    The original tool keeps its store at ``Documents/NIT Store``. Returns the
    first candidate that looks like a store (has a ``Data`` subfolder) so the
    import dialog can pre-fill it — a one-click migration for existing users.
    """
    from nwnfile.locations import HostOS, user_documents_dir

    documents = user_documents_dir(HostOS.current()).parent
    candidates = [documents / "NIT Store", Path.home() / "Documents" / "NIT Store"]
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "Data").is_dir():
            return candidate
    return None


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


def default_game_user_path() -> Path | None:
    """The NWN:EE user-files folder if it exists on disk (for first-run auto-config).

    NWN:EE keeps the *installed* haks/override/tlk plus saves/localvault in a
    per-user folder (``Documents/Neverwinter Nights``), separate from the game
    install. Recording it in settings engages the Mapper's EE folder split so
    already-installed mods are detected (see the installed-mods fix). Returns
    ``None`` when the standard folder isn't present — the user can still set it
    later via the Locations page, and scans fall back to the single-root layout.
    """
    from nwnfile.locations import HostOS, user_documents_dir

    candidate = user_documents_dir(HostOS.current())
    return candidate if candidate.is_dir() else None


def configure_profile(
    nwn_path: str,
    profile_name: str,
    *,
    store_root: str | None = None,
    settings: Settings | None = None,
    settings_path: Path | None = None,
) -> ProfileController:
    """Persist a game path + profile choice, create the store tree, and open it.

    Used by the first-run / "Set Up Profile" flow: records the selection in the
    isolated settings file (never in the game folder), ensures the store and the
    profile's mods directory exist, then returns a live controller. When the game
    user folder hasn't been configured yet, the standard NWN:EE user folder is
    auto-detected (:func:`default_game_user_path`) so the EE folder split engages
    and installed mods are recognised out of the box.
    """
    settings = settings or load_settings(settings_path)
    settings.nwn_path = nwn_path
    settings.active_profile = profile_name
    if store_root:
        settings.store_root = store_root
    if not settings.game_user_path:
        user_dir = default_game_user_path()
        if user_dir is not None:
            settings.game_user_path = str(user_dir)

    store = settings.resolved_store()
    store.ensure()
    store.profile_dir(profile_name).mkdir(parents=True, exist_ok=True)
    save_settings(settings, settings_path)

    controller = bootstrap_controller(settings, discover=lambda: [])
    if controller is None:  # pragma: no cover - guaranteed configured above
        raise RuntimeError("profile configuration did not yield a controller")
    return controller
