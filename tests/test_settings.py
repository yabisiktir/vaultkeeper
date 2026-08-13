"""Tests for the single isolated settings store."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings, load_settings, save_settings


def test_defaults() -> None:
    s = Settings()
    assert s.version == 1
    assert s.recycle_on_delete is True
    assert s.validate_game_config_on_startup is True
    assert s.nwn_path is None


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = Settings(nwn_path="/games/nwn", active_profile="My Mods", recycle_on_delete=False)
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.nwn_path == "/games/nwn"
    assert loaded.active_profile == "My Mods"
    assert loaded.recycle_on_delete is False


def test_missing_file_yields_defaults(tmp_path: Path) -> None:
    loaded = load_settings(tmp_path / "none.json")
    assert loaded == Settings()


def test_unknown_keys_preserved(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    # Simulate a file written by a newer version with an extra field.
    from vaultkeeper.persistence.json_store import write_json

    write_json(path, {"version": 1, "nwn_path": "/g", "future_flag": 42})
    loaded = load_settings(path)
    assert loaded.nwn_path == "/g"
    save_settings(loaded, path)
    from vaultkeeper.persistence.json_store import read_json

    reread = read_json(path)
    assert reread["future_flag"] == 42  # round-tripped despite being unmodelled


def test_resolved_store_uses_custom_root(tmp_path: Path) -> None:
    s = Settings(store_root=str(tmp_path / "MyStore"))
    store = s.resolved_store()
    assert store.root == tmp_path / "MyStore"
    assert store.profiles == tmp_path / "MyStore/Profiles"


def test_development_folder_settings_default_off_and_roundtrip(tmp_path: Path) -> None:
    s = Settings()
    assert s.enable_development_folder is False
    assert s.debug_options_menu is False
    s.enable_development_folder = True
    s.debug_options_menu = True
    path = tmp_path / "settings.json"
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.enable_development_folder is True
    assert loaded.debug_options_menu is True


def test_disable_ee_detection_defaults_off_and_roundtrips(tmp_path: Path) -> None:
    s = Settings()
    assert s.disable_ee_detection is False
    s.disable_ee_detection = True
    path = tmp_path / "settings.json"
    save_settings(s, path)
    assert load_settings(path).disable_ee_detection is True


def test_class_level_editing_defaults_off_and_roundtrips(tmp_path: Path) -> None:
    s = Settings()
    assert s.enable_class_level_editing is False
    s.enable_class_level_editing = True
    path = tmp_path / "settings.json"
    save_settings(s, path)
    assert load_settings(path).enable_class_level_editing is True
