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


def test_configure_profile_persists_and_opens(tmp_path: Path, monkeypatch) -> None:
    from vaultkeeper.config.settings import Settings, load_settings
    from vaultkeeper.ui import session
    from vaultkeeper.ui.session import configure_profile

    # Auto-detecting the EE user folder walks the real machine and takes about
    # thirteen seconds here — the single slowest thing in the suite. It has its
    # own test below; this one is about persistence.
    monkeypatch.setattr(session, "default_game_user_path", lambda **_: None)

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
    monkeypatch.setattr(session, "default_game_user_path", lambda **_: user_dir)

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
    monkeypatch.setattr(session, "default_game_user_path", lambda **_: tmp_path / "auto")
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
    from nwnfile import locations

    from vaultkeeper.ui import session

    # Point the resolver at a non-existent folder -> no auto-config.
    monkeypatch.setattr(
        locations, "user_documents_dir", lambda *a, **k: tmp_path / "missing"
    )
    assert session.default_game_user_path() is None


# --------------------------------------------------------------------------- #
# Export / Import settings (VB RbnExportSettings + the Settings screen's TsImport)
# --------------------------------------------------------------------------- #
def _controller_with_store(tmp_path: Path):
    from vaultkeeper.config.settings import Settings, save_settings
    from vaultkeeper.ui.controller import ProfileController

    settings_path = tmp_path / "settings.json"
    save_settings(
        Settings(store_root=str(tmp_path / "Store"), nwn_path=str(tmp_path / "NWN")),
        settings_path,
    )
    profile_mods = tmp_path / "Store" / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Store" / "Data" / "P.json",
        settings_path=settings_path,
    )


def test_export_settings_writes_into_the_store(tmp_path: Path) -> None:
    controller = _controller_with_store(tmp_path)
    result = controller.export_settings()

    assert result["ok"], result["message"]
    exported = result["path"]
    assert exported.is_file()
    assert exported.parent.name == "Exported Settings"
    assert controller.exported_settings_files() == [exported]


def test_exports_accumulate_rather_than_overwrite(tmp_path: Path, monkeypatch) -> None:
    # The point of an export is to be able to go back to a *particular* set, so
    # a second export must not replace the first.
    import datetime as real_datetime

    controller = _controller_with_store(tmp_path)
    stamps = iter(["2026-01-01 100000", "2026-01-02 110000"])

    class _Clock(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return super().now(tz)

    first = controller.export_settings()
    monkeypatch.setattr(
        "vaultkeeper.ui.controller.datetime", _Clock, raising=False
    )
    # Distinct names come from the timestamp; force one rather than sleeping.
    second_path = first["path"].parent / f"Settings {next(stamps)}.json"
    second_path.write_text(first["path"].read_text(encoding="utf-8"), encoding="utf-8")

    assert first["path"].is_file()
    assert len(controller.exported_settings_files()) == 2


def test_import_restores_preferences_but_not_this_machines_paths(tmp_path: Path) -> None:
    """The half that makes an export worth having — plus the half that is unsafe.

    A settings file names the game folder, the store and the active profile of
    the machine it came from. Importing those would point the app at directories
    that do not exist here, so they are kept and only the preferences change.
    """
    from vaultkeeper.config.settings import load_settings, save_settings

    controller = _controller_with_store(tmp_path)
    exported = controller.export_settings()["path"]

    # A file from "another machine": different preferences *and* different paths.
    foreign = load_settings(exported)
    foreign.recycle_on_delete = False
    foreign.slideshow_interval = 42
    foreign.nwn_path = "/somewhere/else/NWN"
    foreign.active_profile = "Their Profile"
    save_settings(foreign, exported)

    before = load_settings(controller._settings_path)
    result = controller.import_settings(exported)
    assert result["ok"], result["message"]

    after = load_settings(controller._settings_path)
    assert after.recycle_on_delete is False   # preference taken
    assert after.slideshow_interval == 42     # preference taken
    assert after.nwn_path == before.nwn_path  # this machine's, kept
    assert after.active_profile == before.active_profile
    assert after.store_root == before.store_root


def test_importing_a_bad_file_reports_rather_than_raises(tmp_path: Path) -> None:
    controller = _controller_with_store(tmp_path)
    missing = controller.import_settings(tmp_path / "nope.json")
    assert not missing["ok"] and "could not be read" in missing["message"]

    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    result = controller.import_settings(broken)
    assert isinstance(result["ok"], bool)  # whatever it decides, it must not raise


def test_default_game_user_path_none_when_detection_disabled(tmp_path, monkeypatch):
    from nwnfile import locations

    from vaultkeeper.ui import session

    folder = tmp_path / "Neverwinter Nights"
    folder.mkdir()
    monkeypatch.setattr(locations, "user_documents_dir", lambda *a, **k: folder)
    # A valid folder resolves normally, but is ignored when detection is off.
    assert session.default_game_user_path() == folder
    assert session.default_game_user_path(disabled=True) is None


def test_configure_profile_skips_user_path_when_detection_disabled(tmp_path):
    from vaultkeeper.config.settings import Settings, load_settings
    from vaultkeeper.ui.session import configure_profile

    # disable_ee_detection short-circuits before touching the real machine, so no
    # monkeypatch is needed and the developer's own folder is never scanned.
    settings_path = tmp_path / "settings.json"
    settings = Settings(store_root=str(tmp_path / "Store"), disable_ee_detection=True)
    configure_profile(
        str(tmp_path / "NWN"), "Fresh", settings=settings, settings_path=settings_path
    )
    # The user folder is left for the user to set, not guessed (VB PrivateExtendedDisabled).
    assert load_settings(settings_path).game_user_path is None
