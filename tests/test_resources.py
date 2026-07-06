"""Tests for the bundled-resource loader."""

from __future__ import annotations

from vaultkeeper.ui import resources as R


def test_app_icon_loads(qtbot):
    assert not R.app_icon().isNull()


def test_known_icons_exist(qtbot):
    # A spread of icons the ribbon/toolbar/menus reference by file name.
    for name in ("PlayBlue32x", "Anneal_16x", "Install Package 16x16", "Uninstall"):
        assert R.icon_exists(name), f"missing bundled icon: {name}"


def test_name_map_fallback(qtbot):
    # Mapped code-name -> file with spaces.
    assert R.icon_exists("Refresh Arrow Blue")
    assert not R.get_icon("Refresh Arrow Blue").isNull()


def test_space_underscore_fallback(qtbot):
    # "featinfo2_16" is referenced with an underscore; resolves regardless.
    assert R.resolve_path("Anneal_16x") is not None


def test_missing_icon_is_empty_not_error(qtbot):
    assert R.get_icon("definitely_not_a_real_icon_xyz").isNull()
    assert not R.icon_exists("definitely_not_a_real_icon_xyz")


def test_icons_class_names_resolve(qtbot):
    # Every string constant on the Icons registry should back a real asset.
    missing = []
    for attr in dir(R.Icons):
        if attr.startswith("_"):
            continue
        value = getattr(R.Icons, attr)
        if isinstance(value, str) and not R.icon_exists(value):
            missing.append((attr, value))
    assert not missing, f"Icons entries with no asset: {missing}"


def test_icon_is_cached(qtbot):
    first = R.get_icon("PlayBlue32x")
    second = R.get_icon("PlayBlue32x")
    assert first is second
