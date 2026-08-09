"""The test suite must not touch the developer's own Vaultkeeper store.

``conftest._isolate_store`` redirects the roots per test. It used to patch only
``app_paths._home``, which is enough on macOS and not on Windows or Linux, where
``config_root``/``data_root``/``cache_root`` prefer environment variables and
only fall back to the home directory. Every Windows test therefore shared — and
wrote into — the machine's real %APPDATA%, which stayed hidden until a test
saved a setting that a later test read back.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper import app_paths


@pytest.mark.parametrize(
    "root", [app_paths.config_root, app_paths.data_root, app_paths.cache_root]
)
def test_every_root_is_inside_the_temporary_home(root, tmp_path_factory):
    """Whatever the platform decides, it must land under the patched home."""
    home = app_paths._home()
    resolved = root()
    assert home in resolved.parents or resolved == home, (
        f"{root.__name__}() escaped the test home: {resolved}"
    )


def test_the_settings_file_is_isolated_too():
    from vaultkeeper.config.settings import Settings

    settings_file = Settings().resolved_store().settings_file
    assert app_paths._home() in Path(settings_file).parents


def test_a_saved_setting_does_not_leak_into_the_next_test():
    """Half of the pair: this one writes."""
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.pinned_recent_mods = ["Written By The Previous Test"]
    save_settings(settings)
    assert load_settings().pinned_recent_mods == ["Written By The Previous Test"]


def test_the_next_test_sees_none_of_it():
    """And the other half: this one reads, and must see a clean slate."""
    from vaultkeeper.config.settings import load_settings

    assert load_settings().pinned_recent_mods == []
