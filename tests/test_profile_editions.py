"""A profile's edition is fixed when it is made (definenewprofiles.htm).

"You cannot change the Profile Type after the Profile has been created." The
port named the profile after the detected edition and then opened every profile
as Enhanced Edition regardless — so a classic 1.69 profile got EE's folder
layout, which puts its mods somewhere the game does not read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.config.settings import Settings, load_settings, save_settings
from vaultkeeper.ui.session import configure_profile, profile_is_ee


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    s = Settings()
    s.store_root = str(tmp_path / "Store")
    s.game_user_path = str(tmp_path / "user")
    return s


def _configure(tmp_path: Path, settings: Settings, name: str, *, is_ee: bool):
    return configure_profile(
        str(tmp_path / "NWN"),
        name,
        is_ee=is_ee,
        settings=settings,
        settings_path=tmp_path / "settings.json",
    )


def test_a_classic_profile_is_opened_as_classic(tmp_path, settings):
    controller = _configure(tmp_path, settings, "Classic", is_ee=False)
    assert controller.ctx.is_ee is False


def test_an_enhanced_profile_is_opened_as_enhanced(tmp_path, settings):
    controller = _configure(tmp_path, settings, "EE", is_ee=True)
    assert controller.ctx.is_ee is True


def test_the_edition_is_recorded_against_the_profile(tmp_path, settings):
    _configure(tmp_path, settings, "Classic", is_ee=False)
    saved = load_settings(tmp_path / "settings.json")
    assert saved.profile_editions["Classic"] is False


def test_two_profiles_keep_their_own_editions(tmp_path, settings):
    _configure(tmp_path, settings, "Classic", is_ee=False)
    _configure(tmp_path, settings, "EE", is_ee=True)
    saved = load_settings(tmp_path / "settings.json")

    assert profile_is_ee("Classic", saved) is False
    assert profile_is_ee("EE", saved) is True


def test_a_profile_with_no_record_is_treated_as_enhanced(tmp_path, settings):
    """Profiles made before this was recorded were opened as EE. Changing that
    retrospectively would relocate every file they know about."""
    save_settings(settings, tmp_path / "settings.json")
    assert profile_is_ee("Older Profile", load_settings(tmp_path / "settings.json"))


def test_the_layout_actually_differs(tmp_path, settings):
    """Not a label: the two editions look for mods in different places."""
    classic = _configure(tmp_path, settings, "Classic", is_ee=False)
    classic_hak = classic.ctx.game_folders["hak"]

    ee = _configure(tmp_path, settings, "EE", is_ee=True)
    ee_hak = ee.ctx.game_folders["hak"]

    assert classic_hak != ee_hak
    assert str(tmp_path / "NWN") in str(classic_hak), "classic installs into the game"
    assert str(tmp_path / "user") in str(ee_hak), "EE installs into the user folder"
