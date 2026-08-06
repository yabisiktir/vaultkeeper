"""Tests for EE folder resolution: nwn.ini [Alias] reader + Mapper.nwn_folder_paths.

Grounds the fix that lets Vaultkeeper find already-installed mods on NWN:EE (where
mod content lives in the user dir, not the install dir). See the module docstrings
in ``game/nwn_folders.py`` and ``Mapper.nwn_folder_paths``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests import real_data
from vaultkeeper.core.mapper import Mapper
from vaultkeeper.game.nwn_folders import foreign_alias_values, read_alias_locations

# The host's own root, so the fixture's "absolute" entries really are absolute
# wherever the suite runs. A rooted-but-driveless path like "/Users/x" is
# absolute on POSIX but *relative* on Windows, which has no drive to root it —
# there the reader would (correctly) resolve it against the user dir, and the
# test would be asserting the wrong branch rather than finding a bug.
_ROOT = Path(Path.cwd().anchor)  # "/" on POSIX, "C:\\" on Windows
_DOCS = _ROOT / "Users" / "x" / "Documents" / "Neverwinter Nights"
_NWM = _ROOT / "Users" / "x" / "Library" / "NWN" / "data" / "nwm"

_ALIAS_INI = f"""\
[Settings]
Foo=Bar

[Alias]
HD0={_DOCS}
SAVES={_DOCS / "saves"}
HAK={_DOCS / "hak"}
OVERRIDE={_DOCS / "override"}
MODULES={_DOCS / "modules"}
NWMFiles={_NWM}
RELHAK=relhaks

[Other]
Ignore=me
"""


def test_read_alias_locations_parses_section(tmp_path: Path) -> None:
    (tmp_path / "nwn.ini").write_text(_ALIAS_INI, encoding="utf-8")
    locs = read_alias_locations(tmp_path)

    # Moddable folders are present, keyed lower-case.
    assert locs["hak"] == _DOCS / "hak"
    assert locs["override"] == _DOCS / "override"
    assert locs["modules"] == _DOCS / "modules"
    # NWMFiles is normalised to the "nwm" folder identifier.
    assert locs["nwm"] == _NWM
    # CD/HD markers and saves are skipped.
    assert "hd0" not in locs
    assert "saves" not in locs
    # A relative value is resolved against the user dir.
    assert locs["relhak"] == tmp_path / "relhaks"
    # Entries outside the [Alias] section are ignored.
    assert "foo" not in locs and "ignore" not in locs


def test_read_alias_locations_missing_file(tmp_path: Path) -> None:
    assert read_alias_locations(tmp_path) == {}


# --------------------------------------------------------------------------- #
# Aliases written by the other operating system
# --------------------------------------------------------------------------- #
# Reported from a Windows 11 VM whose user folder was the host Mac's Documents,
# mounted over a share. nwn.ini stores absolute, platform-specific paths, so the
# Windows app was reading the Mac's aliases. No mod was ever found, and
# rebuilding the database could not help: the folder being scanned did not exist.
_FOREIGN_INI = """\
[Alias]
HAK={foreign}/hak
OVERRIDE={foreign}/override
RELHAK=relhaks
"""

_POSIX_ALIAS = "/Users/x/Documents/Neverwinter Nights"
_WINDOWS_ALIAS = r"C:\Users\x\Documents\Neverwinter Nights"

#: Whichever form the *running* host did not write.
_FOREIGN = _POSIX_ALIAS if os.name == "nt" else _WINDOWS_ALIAS


def test_an_alias_from_another_os_is_ignored_not_mangled(tmp_path: Path) -> None:
    """The bug: a foreign absolute path was silently joined onto the user dir.

    ``Path("/Users/x/…").is_absolute()`` is False on Windows — a leading slash
    with no drive is rooted, not absolute — so the old code took the "relative"
    branch and built ``\\\\mac\\Home\\Users\\x\\…``, splicing the POSIX path onto
    the share root. The same happens in reverse: a ``C:\\…`` value on POSIX is
    not absolute either, and would be joined just as wrongly.

    Dropping the entry is what makes it right, because the caller then falls
    back to ``user_dir/<name>`` — where the files actually are.
    """
    (tmp_path / "nwn.ini").write_text(
        _FOREIGN_INI.format(foreign=_FOREIGN), encoding="utf-8"
    )
    locs = read_alias_locations(tmp_path)

    assert "hak" not in locs, "a foreign alias must be dropped, not resolved"
    assert "override" not in locs
    # Specifically, it must never have been joined onto the user dir.
    assert not any(str(p).startswith(str(tmp_path)) and "Documents" in str(p)
                   for p in locs.values())
    # A genuinely relative entry still resolves — only foreign ones are dropped.
    assert locs["relhak"] == tmp_path / "relhaks"


def test_an_alias_this_os_wrote_is_still_honoured(tmp_path: Path) -> None:
    native = _WINDOWS_ALIAS if os.name == "nt" else _POSIX_ALIAS
    (tmp_path / "nwn.ini").write_text(
        _FOREIGN_INI.format(foreign=native), encoding="utf-8"
    )
    locs = read_alias_locations(tmp_path)

    assert locs["hak"] == Path(native) / "hak"
    assert locs["override"] == Path(native) / "override"


def test_foreign_aliases_are_reported_so_the_user_can_be_told(tmp_path: Path) -> None:
    # Dropping them fixes the scan, but the user still has a real problem: the
    # two installs are fighting over one nwn.ini, and the *game* will refuse to
    # start on whichever one did not write it last.
    (tmp_path / "nwn.ini").write_text(
        _FOREIGN_INI.format(foreign=_FOREIGN), encoding="utf-8"
    )
    foreign = foreign_alias_values(tmp_path)

    assert set(foreign) == {"hak", "override"}
    assert foreign["hak"] == f"{_FOREIGN}/hak"
    assert foreign_alias_values(tmp_path / "nowhere") == {}


@pytest.mark.parametrize(
    ("value", "windows", "posix"),
    [
        (r"C:\Games\NWN", True, False),
        ("C:/Games/NWN", True, False),
        (r"\\server\share\NWN", True, False),
        ("/Users/x/NWN", False, True),
        ("//server/share/NWN", False, False),  # UNC in disguise: neither claims it
        ("relhaks", False, False),
        ("./relhaks", False, False),
    ],
)
def test_which_os_a_value_belongs_to(value: str, windows: bool, posix: bool) -> None:
    # Pinned explicitly rather than left to Path, whose idea of "absolute"
    # changes with the host — which is the whole reason for the bug above.
    from vaultkeeper.game.nwn_folders import _POSIX_ABSOLUTE, _WINDOWS_ABSOLUTE

    assert bool(_WINDOWS_ABSOLUTE.match(value)) is windows
    assert bool(_POSIX_ABSOLUTE.match(value)) is posix


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


# --- Real-data golden test (opt-in; see tests/real_data.py) --------------- #
_NIT_STORE = real_data.nit_store()
_USER_DIR = real_data.nwn_user_dir()
_INSTALL = real_data.nwn_install()


#: This one reads a real NIT Store and a real NWN:EE install, so it runs only
#: where those are provided. The skipif used to sit on the helper below, where
#: pytest does not look for marks — so the test ran everywhere and failed on
#: every CI platform, asserting about a store that was not there.
_HAVE_REAL_DATA = not real_data.missing(_NIT_STORE, _USER_DIR, _INSTALL)


def _resolved(pd, *, is_ee: bool) -> tuple[list[str], list[str]]:
    """``(resolved, missed)`` mod names under one folder-resolution mode."""
    mapper = Mapper(is_ee=is_ee)
    folders = mapper.nwn_folder_paths(
        _INSTALL,
        user_dir=_USER_DIR if is_ee else None,
        alias_locations=read_alias_locations(_USER_DIR) if is_ee else None,
    )
    resolved: list[str] = []
    missed: list[str] = []
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
        (resolved if (total and present == total) else missed).append(name)
    return resolved, missed


@pytest.mark.skipif(not _HAVE_REAL_DATA, reason=real_data.REASON)
def test_ee_resolution_lights_up_real_installed_mods() -> None:
    """With EE resolution, the owner's real imported mods resolve on disk.

    Asserted as a property rather than a count: the store is the owner's live
    data and its size changes, so a golden number here goes stale on its own and
    says nothing about the code. What matters is that EE resolution — which looks
    in the user directory, where EE actually installs content — finds them, and
    that pre-EE resolution finds nothing at all. The only mods it cannot place are
    the ini-file restorers, which are config files handled by the
    config-isolation guard rather than game installs.
    """
    from vaultkeeper.persistence.nrbf.migrate import migrate_profile

    pd = migrate_profile(_NIT_STORE, "Enhanced Edition Mods")
    resolved, missed = _resolved(pd, is_ee=True)
    before, _ = _resolved(pd, is_ee=False)

    assert not before, "without EE resolution nothing resolves — the bug this fixed"
    assert resolved, "with it, the owner's installed mods are found"
    assert all("INI" in name.upper() for name in missed), (
        f"only the ini restorers may miss; got {missed}"
    )
