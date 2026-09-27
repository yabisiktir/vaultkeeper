"""nwn.ini aliases that lead outside the profile's user folder (VB ``PopulateLocations``).

NIT points each alias at the same-named sub-folder of the profile's own user
folder on every load. A folder copied for a test profile otherwise keeps the
original's absolute aliases, so the game and every install use the original.
Vaultkeeper asks first; see ``ui/alias_repair.py``.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.config.settings import Settings
from vaultkeeper.game.nwn_folders import read_alias_locations, stray_alias_updates
from vaultkeeper.ui.session import bootstrap_controller


def _ini(user: Path, aliases: dict[str, str]) -> None:
    user.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"{k}={v}" for k, v in aliases.items())
    (user / "nwn.ini").write_text(f"[Alias]\n{body}\n[Game Options]\nX=1\n")


def test_aliases_into_another_folder_are_found(tmp_path: Path) -> None:
    live, copy = tmp_path / "live", tmp_path / "copy"
    _ini(copy, {
        "HD0": str(live),
        "HAK": str(live / "hak"),
        "OVERRIDE": str(copy / "override"),
        "SAVES": str(live / "saves___"),
        "CD0": str(tmp_path / "install"),
        "TLK": "tlk",
    })

    assert stray_alias_updates(copy) == {"HD0": str(copy), "HAK": str(copy / "hak")}


def test_a_folder_whose_aliases_are_its_own_needs_nothing(tmp_path: Path) -> None:
    user = tmp_path / "user"
    _ini(user, {"HD0": str(user), "HAK": str(user / "hak"), "SAVES": str(user / "saves___")})
    assert stray_alias_updates(user) == {}


def _settings(tmp_path: Path, user: Path) -> Settings:
    settings = Settings()
    settings.store_root = str(tmp_path / "Store")
    settings.active_profile = "Test"
    settings.nwn_path = str(tmp_path / "install")
    settings.game_user_path = str(user)
    (tmp_path / "install").mkdir(exist_ok=True)
    return settings


def test_the_profile_opens_on_its_own_folder_once_agreed(tmp_path: Path) -> None:
    live, copy = tmp_path / "live", tmp_path / "copy"
    _ini(copy, {"HD0": str(live), "HAK": str(live / "hak")})
    asked = []

    controller = bootstrap_controller(
        _settings(tmp_path, copy),
        discover=lambda: [],
        confirm_alias_repair=lambda d, u: asked.append(u) or True,
    )

    assert asked == [{"HD0": str(copy), "HAK": str(copy / "hak")}]
    assert controller.ctx.game_folders["hak"] == copy / "hak"
    assert read_alias_locations(copy)["hak"] == copy / "hak"
    assert (copy / "nwn.ini.bak").read_text().count(str(live)) == 2
    assert "[Game Options]\nX=1" in (copy / "nwn.ini").read_text()


def test_declining_leaves_nwn_ini_alone(tmp_path: Path) -> None:
    live, copy = tmp_path / "live", tmp_path / "copy"
    _ini(copy, {"HAK": str(live / "hak")})
    before = (copy / "nwn.ini").read_text()

    bootstrap_controller(
        _settings(tmp_path, copy), discover=lambda: [], confirm_alias_repair=lambda d, u: False
    )

    assert (copy / "nwn.ini").read_text() == before
    assert not (copy / "nwn.ini.bak").exists()


def test_saves_follow_the_saves_alias(tmp_path: Path) -> None:
    # VB SetGameSavesPath: the game, and NIT, use nwn.ini's SAVES alias.
    from vaultkeeper.ui.controller import ProfileController

    user = tmp_path / "user"
    _ini(user, {"HD0": str(user), "SAVES": str(user / "saves___")})
    for name in ("000001 - One", "000002 - Two"):
        (user / "saves___" / name).mkdir(parents=True)
    (user / "saves").mkdir()
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=user,
    )

    assert c.game_saves_dir() == user / "saves___"
    assert c.saves_count() == 2
    assert c.play_loop.saves_dir == user / "saves___"


def test_without_a_saves_alias_the_default_folder_is_used(tmp_path: Path) -> None:
    from vaultkeeper.game.nwn_folders import saves_folder

    user = tmp_path / "user"
    _ini(user, {"HAK": str(user / "hak")})
    assert saves_folder(user) == user / "saves"
    assert saves_folder(tmp_path / "no ini") == tmp_path / "no ini" / "saves"
