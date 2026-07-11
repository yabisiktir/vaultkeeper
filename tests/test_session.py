"""Tests for the session bootstrap (settings + discovery -> controller)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings
from vaultkeeper.core import constants as C
from vaultkeeper.ui.session import bootstrap_controller


def _make_mod(profile_mods: Path, name: str, rel: str, data: bytes) -> None:
    target = profile_mods / name / C.MOD_INSTALLER_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def test_returns_none_when_unconfigured() -> None:
    # No game path and discovery finds nothing -> nothing to open.
    settings = Settings()
    assert bootstrap_controller(settings, discover=lambda: []) is None


def test_returns_none_without_active_profile(tmp_path: Path) -> None:
    settings = Settings(nwn_path=str(tmp_path / "NWN"))  # game set, no profile
    assert bootstrap_controller(settings, discover=lambda: []) is None


def test_opens_configured_profile(tmp_path: Path) -> None:
    store_root = tmp_path / "Store"
    game_root = tmp_path / "NWN"
    settings = Settings(
        store_root=str(store_root),
        nwn_path=str(game_root),
        active_profile="My Mods",
    )
    # Create a mod under the profile's mods directory.
    profile_mods = store_root / "Profiles" / "My Mods"
    _make_mod(profile_mods, "Alpha", "hak/a.hak", b"AAA")

    controller = bootstrap_controller(settings, discover=lambda: [])
    assert controller is not None
    assert "Alpha" in controller.pd.mod_keys
    # Store path is under the resolved store's Data dir.
    assert controller.store_path == store_root / "Data" / "My Mods.json"


def test_configure_profile_persists_and_opens(tmp_path: Path) -> None:
    from vaultkeeper.config.settings import Settings, load_settings
    from vaultkeeper.ui.session import configure_profile

    settings_path = tmp_path / "settings.json"
    settings = Settings(store_root=str(tmp_path / "Store"))
    controller = configure_profile(
        str(tmp_path / "NWN"), "Fresh", settings=settings, settings_path=settings_path
    )
    assert controller is not None
    # The profile mods directory was created.
    assert (tmp_path / "Store" / "Profiles" / "Fresh").is_dir()
    # Settings were persisted with the game path + active profile.
    reloaded = load_settings(settings_path)
    assert reloaded.active_profile == "Fresh"
    assert reloaded.nwn_path == str(tmp_path / "NWN")


def test_configure_profile_auto_populates_game_user_path(tmp_path, monkeypatch):
    from vaultkeeper.config.settings import Settings, load_settings
    from vaultkeeper.ui import session
    from vaultkeeper.ui.session import configure_profile

    user_dir = tmp_path / "Neverwinter Nights"
    user_dir.mkdir()
    monkeypatch.setattr(session, "default_game_user_path", lambda: user_dir)

    settings_path = tmp_path / "settings.json"
    settings = Settings(store_root=str(tmp_path / "Store"))
    configure_profile(
        str(tmp_path / "NWN"), "Fresh", settings=settings, settings_path=settings_path
    )
    # The EE user folder was recorded so the folder split engages.
    assert load_settings(settings_path).game_user_path == str(user_dir)


def test_configure_profile_keeps_explicit_game_user_path(tmp_path, monkeypatch):
    from vaultkeeper.config.settings import Settings, load_settings
    from vaultkeeper.ui import session
    from vaultkeeper.ui.session import configure_profile

    # Auto-detection must never override a user's explicit choice.
    monkeypatch.setattr(session, "default_game_user_path", lambda: tmp_path / "auto")
    settings_path = tmp_path / "settings.json"
    settings = Settings(
        store_root=str(tmp_path / "Store"),
        game_user_path=str(tmp_path / "chosen"),
    )
    configure_profile(
        str(tmp_path / "NWN"), "Fresh", settings=settings, settings_path=settings_path
    )
    assert load_settings(settings_path).game_user_path == str(tmp_path / "chosen")


def test_default_game_user_path_none_when_absent(tmp_path, monkeypatch):
    from vaultkeeper.game import locations
    from vaultkeeper.ui import session

    # Point the resolver at a non-existent folder -> no auto-config.
    monkeypatch.setattr(
        locations, "user_documents_dir", lambda *a, **k: tmp_path / "missing"
    )
    assert session.default_game_user_path() is None
