"""Finding-3 (settings content gap): new mods honour the default-group preference.

VB ``ConfigDefaultGroup`` lets the user pick a group that newly created mods land
in. The port modelled no such setting (new mods always went to GROUP_NONE); this
adds ``Settings.default_group`` and wires it into ``create_mod``.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings, save_settings
from vaultkeeper.core import constants as C
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, *, default_group: str = "") -> ProfileController:
    pd = ProfileData()
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    settings_path = tmp_path / "settings.json"
    save_settings(Settings(default_group=default_group), settings_path)
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
        settings_path=settings_path,
    )


def test_new_mod_uses_default_group(tmp_path: Path) -> None:
    controller = _controller(tmp_path, default_group="Adventures")
    assert controller.create_mod("Aribeth")
    assert controller.pd.mod_item("Aribeth").group == "Adventures"


def test_new_mod_default_group_empty_is_ungrouped(tmp_path: Path) -> None:
    controller = _controller(tmp_path, default_group="")
    assert controller.create_mod("Aribeth")
    assert controller.pd.mod_item("Aribeth").group == C.GROUP_NONE


def test_explicit_group_overrides_default(tmp_path: Path) -> None:
    controller = _controller(tmp_path, default_group="Adventures")
    assert controller.create_mod("Aribeth", group="Campaigns")
    assert controller.pd.mod_item("Aribeth").group == "Campaigns"
