"""Tests for editable mod properties (Rating/Weapon/Levels/Henchmen)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.profile_data import ProfileData
from vaultkeeper.core.state import Ratings, Weapon
from vaultkeeper.persistence.profile_store import save_profile
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.mod_properties import ModPropertiesDialog


def _controller(tmp_path: Path, md: ModData) -> ProfileController:
    pd = ProfileData()
    pd.add_mod(md)
    pd.ensure_mandatory_groups()
    store = tmp_path / "Data" / "P.json"
    save_profile(pd, store)
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=store,
    )


def test_set_mod_properties_persists(tmp_path: Path) -> None:
    controller = _controller(tmp_path, ModData(group="G", mod_name="M"))
    ok = controller.set_mod_properties(
        "M",
        rating=Ratings.EXCELLENT,
        best_weapon=Weapon.LONG_SWORD,
        level_start=3,
        level_end=12,
        hench_count=2,
    )
    assert ok
    md = controller.pd.mod_item("M")
    assert md.rating == Ratings.EXCELLENT
    assert md.best_weapon == Weapon.LONG_SWORD
    assert md.level_start == 3
    assert md.level_end == 12
    assert md.hench_count == 2

    # Persisted across reload.
    reloaded = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "mods",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    assert reloaded.pd.mod_item("M").rating == Ratings.EXCELLENT


def test_set_mod_properties_rejects_group_item(tmp_path: Path) -> None:
    controller = _controller(tmp_path, ModData(group="G", mod_name="M"))
    assert controller.set_mod_properties("......000", rating=Ratings.GOOD) is False


def test_mod_properties_getter(tmp_path: Path) -> None:
    md = ModData(group="G", mod_name="M")
    md.rating = Ratings.GOOD
    md.best_weapon = Weapon.DAGGER
    controller = _controller(tmp_path, md)
    props = controller.mod_properties("M")
    assert props["rating"] == Ratings.GOOD
    assert props["best_weapon"] == Weapon.DAGGER
    assert controller.mod_properties("nope") is None


def test_dialog_roundtrips_values(qtbot) -> None:
    props = {
        "rating": Ratings.MEDIUM,
        "best_weapon": Weapon.KATANA,
        "level_start": 5,
        "level_end": -1,  # unspecified
        "hench_count": -1,
    }
    dlg = ModPropertiesDialog("M", props)
    qtbot.addWidget(dlg)
    values = dlg.values()
    assert values["rating"] == Ratings.MEDIUM
    assert values["best_weapon"] == Weapon.KATANA
    assert values["level_start"] == 5
    assert values["level_end"] == -1  # shown as "—"
    assert values["hench_count"] == -1


def test_dialog_edit_changes_values(qtbot) -> None:
    props = {
        "rating": Ratings.NONE,
        "best_weapon": Weapon.NONE,
        "level_start": -1,
        "level_end": -1,
        "hench_count": -1,
    }
    dlg = ModPropertiesDialog("M", props)
    qtbot.addWidget(dlg)
    dlg.rating.setCurrentIndex(dlg.rating.findData(Ratings.BAD))
    dlg.level_start.setValue(1)
    assert dlg.values()["rating"] == Ratings.BAD
    assert dlg.values()["level_start"] == 1
