"""Tests for the legacy NIT Store import session flow (ui/session.py).

Covers migrating a legacy profile's ModData into the native store and listing the
profiles available in a legacy store. The NRBF parse is stubbed (tested elsewhere);
this exercises the migrate -> save-native -> reload wiring.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings, load_settings
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.persistence.nrbf import migrate
from vaultkeeper.persistence.profile_store import load_profile
from vaultkeeper.ui.session import import_legacy_profile, list_legacy_profiles


def _legacy_store(tmp_path: Path, profile: str) -> Path:
    root = tmp_path / "NIT Store"
    (root / "Data" / profile).mkdir(parents=True)
    (root / "Data" / profile / "nit.ModData_Format_002").write_bytes(b"fake")
    return root


def _settings(tmp_path: Path) -> Settings:
    return Settings(store_root=str(tmp_path / "vault-store"))


def test_list_legacy_profiles(tmp_path):
    _legacy_store(tmp_path, "Main")
    (tmp_path / "NIT Store" / "Data" / "Testing").mkdir()
    assert list_legacy_profiles(tmp_path / "NIT Store") == ["Main", "Testing"]


def test_import_writes_native_store(tmp_path, monkeypatch):
    legacy = _legacy_store(tmp_path, "Main")
    monkeypatch.setattr(
        migrate,
        "import_mod_list",
        lambda data: {"Alpha": ModData(group="Adventures", mod_name="Alpha")},
    )
    settings_path = tmp_path / "settings.json"

    target = import_legacy_profile(
        legacy, "Main", settings=_settings(tmp_path), settings_path=settings_path
    )

    assert target.name == "Main.json"
    assert target.is_file()
    pd = load_profile(target)
    assert pd is not None
    assert pd.mod_item("Alpha").group == "Adventures"


def test_import_can_set_active_profile(tmp_path, monkeypatch):
    legacy = _legacy_store(tmp_path, "Main")
    monkeypatch.setattr(migrate, "import_mod_list", lambda data: {})
    settings_path = tmp_path / "settings.json"

    import_legacy_profile(
        legacy,
        "Main",
        settings=_settings(tmp_path),
        settings_path=settings_path,
        make_active=True,
    )
    assert load_settings(settings_path).active_profile == "Main"


def test_import_creates_profile_mods_dir(tmp_path, monkeypatch):
    legacy = _legacy_store(tmp_path, "Main")
    monkeypatch.setattr(migrate, "import_mod_list", lambda data: {})
    settings = _settings(tmp_path)

    import_legacy_profile(
        legacy, "Main", settings=settings, settings_path=tmp_path / "s.json"
    )
    assert settings.resolved_store().profile_dir("Main").is_dir()
