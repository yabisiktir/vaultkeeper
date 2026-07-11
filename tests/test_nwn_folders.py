"""Tests for EE folder resolution: nwn.ini [Alias] reader + Mapper.nwn_folder_paths.

Grounds the fix that lets Vaultkeeper find already-installed mods on NWN:EE (where
mod content lives in the user dir, not the install dir). See the module docstrings
in ``game/nwn_folders.py`` and ``Mapper.nwn_folder_paths``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core.mapper import Mapper
from vaultkeeper.game.nwn_folders import read_alias_locations

_ALIAS_INI = """\
[Settings]
Foo=Bar

[Alias]
HD0=/Users/x/Documents/Neverwinter Nights
SAVES=/Users/x/Documents/Neverwinter Nights/saves
HAK=/Users/x/Documents/Neverwinter Nights/hak
OVERRIDE=/Users/x/Documents/Neverwinter Nights/override
MODULES=/Users/x/Documents/Neverwinter Nights/modules
NWMFiles=/Users/x/Library/NWN/data/nwm
RELHAK=relhaks

[Other]
Ignore=me
"""


def test_read_alias_locations_parses_section(tmp_path: Path) -> None:
    (tmp_path / "nwn.ini").write_text(_ALIAS_INI, encoding="utf-8")
    locs = read_alias_locations(tmp_path)

    # Moddable folders are present, keyed lower-case.
    assert locs["hak"] == Path("/Users/x/Documents/Neverwinter Nights/hak")
    assert locs["override"] == Path("/Users/x/Documents/Neverwinter Nights/override")
    assert locs["modules"] == Path("/Users/x/Documents/Neverwinter Nights/modules")
    # NWMFiles is normalised to the "nwm" folder identifier.
    assert locs["nwm"] == Path("/Users/x/Library/NWN/data/nwm")
    # CD/HD markers and saves are skipped.
    assert "hd0" not in locs
    assert "saves" not in locs
    # A relative value is resolved against the user dir.
    assert locs["relhak"] == tmp_path / "relhaks"
    # Entries outside the [Alias] section are ignored.
    assert "foo" not in locs and "ignore" not in locs


def test_read_alias_locations_missing_file(tmp_path: Path) -> None:
    assert read_alias_locations(tmp_path) == {}


def test_folder_paths_standard_layout_default() -> None:
    """No user_dir -> every folder under game_root (backward compatible)."""
    mapper = Mapper(is_ee=True)
    root = Path("/game/nwn")
    paths = mapper.nwn_folder_paths(root)
    assert paths["nwn"] == root
    assert paths["hak"] == root / "hak"
    assert paths["ovr"] == root / "ovr"
    assert paths["mod"] == root / "mod"


def test_folder_paths_non_ee_ignores_user_dir() -> None:
    """A non-EE mapper keeps the single-root layout even with a user dir."""
    mapper = Mapper(is_ee=False)
    root = Path("/game/nwn")
    user = Path("/home/user/Documents/Neverwinter Nights")
    paths = mapper.nwn_folder_paths(root, user_dir=user)
    assert paths["hak"] == root / "hak"


def test_folder_paths_ee_splits_user_and_install() -> None:
    mapper = Mapper(is_ee=True)
    install = Path("/steam/Neverwinter Nights")
    user = Path("/home/user/Documents/Neverwinter Nights")
    paths = mapper.nwn_folder_paths(install, user_dir=user)

    # EE data sub-folders live under the install's data dir.
    assert paths["mod"] == install / "data" / "mod"
    assert paths["nwm"] == install / "data" / "nwm"
    assert paths["mus"] == install / "data" / "mus"
    assert paths["txpk"] == install / "data" / "txpk"
    # ovr is the install-side EE override.
    assert paths["ovr"] == install / "ovr"
    # The root marker stays the install root.
    assert paths["nwn"] == install
    # User content resolves under the user dir.
    assert paths["hak"] == user / "hak"
    assert paths["tlk"] == user / "tlk"
    assert paths["override"] == user / "override"


def test_folder_paths_ee_alias_overrides_user_folder() -> None:
    mapper = Mapper(is_ee=True)
    install = Path("/steam/Neverwinter Nights")
    user = Path("/home/user/Documents/Neverwinter Nights")
    aliases = {"hak": Path("/relocated/haks")}
    paths = mapper.nwn_folder_paths(install, user_dir=user, alias_locations=aliases)
    assert paths["hak"] == Path("/relocated/haks")
    # A non-aliased folder still falls back to the user dir.
    assert paths["tlk"] == user / "tlk"


def test_folder_paths_ee_library_override() -> None:
    """ee_library separates the base-data root from the game root."""
    mapper = Mapper(is_ee=True)
    root = Path("/steam/Neverwinter Nights")
    user = Path("/home/user/Documents/Neverwinter Nights")
    lib = Path("/steam/Neverwinter Nights/lib")
    paths = mapper.nwn_folder_paths(root, user_dir=user, ee_library=lib)
    assert paths["mod"] == lib / "data" / "mod"
    assert paths["ovr"] == lib / "ovr"
    assert paths["nwn"] == root


# --- Real-data golden test (skipif absent) -------------------------------- #
_NIT_STORE = Path("/Users/example/Documents/NIT Store")
_USER_DIR = Path("/Users/example/Documents/Neverwinter Nights")
_INSTALL = Path(
    "/Users/example/Library/Application Support/Steam/steamapps/common/Neverwinter Nights"
)


@pytest.mark.skipif(
    not (_NIT_STORE.is_dir() and _USER_DIR.is_dir() and _INSTALL.is_dir()),
    reason="No real NIT Store / NWN:EE install on this machine",
)
def test_ee_resolution_lights_up_real_installed_mods() -> None:
    """With EE resolution, the owner's real imported mods resolve on disk.

    19 of the 21 imported mods have all their (non-identifier) files present in the
    live game; the 2 misses are the ini-file restorers (config files handled by the
    config-isolation guard, not game installs).
    """
    from vaultkeeper.persistence.nrbf.migrate import migrate_profile

    pd = migrate_profile(_NIT_STORE, "Enhanced Edition Mods")
    mapper = Mapper(is_ee=True)
    folders = mapper.nwn_folder_paths(
        _INSTALL, user_dir=_USER_DIR, alias_locations=read_alias_locations(_USER_DIR)
    )

    installed = 0
    for name in pd.mod_keys:
        md = pd.mod_item(name)
        total = present = 0
        for fk in md.files:
            base = folders.get(fk.folder.lower())
            if base is None or fk.folder.lower() == "nitconfig":
                continue  # identifier files are not game-installed
            total += 1
            if (base / fk.filename).exists():
                present += 1
        if total and present == total:
            installed += 1

    assert installed == 19
