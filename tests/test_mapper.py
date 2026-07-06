"""Tests for the Mapper file->folder engine and its predicates."""

from __future__ import annotations

import pytest

from vaultkeeper.core import mapper as M
from vaultkeeper.core.mapper import Mapper


@pytest.fixture()
def mapper() -> Mapper:
    return Mapper(is_ee=True)


# --- extension mapping (step 5) ------------------------------------------- #
@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/world.mod", M.FOLDER_MODULES),
        ("src/stuff.hak", M.FOLDER_HAK),
        ("src/tex.dds", M.FOLDER_OVERRIDE),
        ("src/hero.tga", M.FOLDER_PORTRAITS),
        ("src/dialog.dlg", M.FOLDER_OVERRIDE),
        ("src/x.tlk", M.FOLDER_TLK),
        ("src/data.bif", M.FOLDER_DATA),
        ("src/save.sqlite3", M.FOLDER_DATABASE),
        ("src/nwn.key", M.FOLDER_ROOT),
        ("src/id.nitins", "nitconfig"),
    ],
)
def test_extension_mapping(mapper: Mapper, path: str, expected: str) -> None:
    assert mapper.get_mapped_folder(path) == expected


def test_unsupported_extension_returns_empty(mapper: Mapper) -> None:
    assert mapper.get_mapped_folder("src/readme.xyz") == ""
    assert mapper.get_mapped_folder("src/tool.exe") == ""


# --- directory mapping precedence (step 2) -------------------------------- #
def test_dir_mapping_takes_precedence(mapper: Mapper) -> None:
    # A .dds normally maps to override, but a file inside a "music" dir maps to music.
    assert mapper.get_mapped_folder("mod/music/track.bmu") == M.FOLDER_MUSIC
    # A .tga inside a known override-alias dir goes to override, not portraits.
    assert (
        mapper.get_mapped_folder("mod/sh_miscmed_override/x.tga") == M.FOLDER_OVERRIDE
    )


def test_dir_mapping_grandparent(mapper: Mapper) -> None:
    # erf dir maps erf files; check parent-name mapping resolves.
    assert mapper.get_mapped_folder("mod/erf/pack.erf") == M.FOLDER_ERF


# --- exception files (step 3) --------------------------------------------- #
def test_exception_file(mapper: Mapper) -> None:
    # dungeonmaster.bic -> dmvault (overrides the .bic -> localvault default)
    assert mapper.get_mapped_folder("mod/localvault/dungeonmaster.bic") == M.FOLDER_DMVAULT
    # dialog.tlk -> nwn root (overrides .tlk -> tlk)
    assert mapper.get_mapped_folder("mod/random/dialog.tlk") == M.FOLDER_ROOT
    # a normal .bic still goes to localvault
    assert mapper.get_mapped_folder("mod/x/hero.bic") == M.FOLDER_LOCALVAULT


# --- folder-move-if-already-there (step 5 tail) --------------------------- #
def test_keeps_file_in_secondary_folder(mapper: Mapper) -> None:
    # .hak default is "hak"; if the file already sits in "patch" (its move target),
    # it stays in patch.
    assert mapper.get_mapped_folder("mod/patch/late.hak") == M.FOLDER_PATCH
    # but a .hak elsewhere maps to hak
    assert mapper.get_mapped_folder("mod/whatever/late.hak") == M.FOLDER_HAK


# --- filename-prefix exceptions (step 6) ---------------------------------- #
def test_prefix_moves_gui_tga_to_override(mapper: Mapper) -> None:
    # A gui_ prefixed .tga is a UI texture -> override, not a portrait.
    assert mapper.get_mapped_folder("mod/x/gui_button.tga") == M.FOLDER_OVERRIDE
    # A voice .wav (c_ prefix) -> override, not ambient.
    assert mapper.get_mapped_folder("mod/x/c_bark.wav") == M.FOLDER_OVERRIDE
    # A normal portrait .tga stays in portraits.
    assert mapper.get_mapped_folder("mod/x/po_hero.tga") == M.FOLDER_PORTRAITS


# --- ERF exclusion (step 4) ----------------------------------------------- #
def test_erf_excluded_on_create_check(mapper: Mapper) -> None:
    # With erf_check, a stray .erf not in texturepacks is excluded.
    assert mapper.get_mapped_folder("mod/random/pack.erf", erf_check=True) == ""
    # In texturepacks it is kept.
    assert (
        mapper.get_mapped_folder("mod/texturepacks/pack.erf", erf_check=True)
        == M.FOLDER_TEXTUREPACKS
    )
    # Without erf_check, normal extension mapping applies.
    assert mapper.get_mapped_folder("mod/random/pack.erf") == M.FOLDER_ERF


def test_erf_not_excluded_when_setting_off() -> None:
    m = Mapper(is_ee=True, exclude_erf=False)
    assert m.get_mapped_folder("mod/random/pack.erf", erf_check=True) == M.FOLDER_ERF


# --- predicates ----------------------------------------------------------- #
def test_mapped_and_extension_predicates(mapper: Mapper) -> None:
    assert mapper.mapped_extension(".HAK")  # case-insensitive
    assert not mapper.mapped_extension(".xyz")
    assert mapper.extension_folder(".mod") == M.FOLDER_MODULES
    assert mapper.get_primary_folder(".tga") == M.FOLDER_PORTRAITS
    assert mapper.get_secondary_folder(".tga") == M.FOLDER_OVERRIDE
    assert mapper.get_secondary_folder(".mod") == ""  # no move defined


def test_move_target_toggles(mapper: Mapper) -> None:
    assert mapper.get_move_target(M.FOLDER_PORTRAITS, ".tga") == M.FOLDER_OVERRIDE
    assert mapper.get_move_target(M.FOLDER_OVERRIDE, ".tga") == M.FOLDER_PORTRAITS


def test_database_and_identifier_predicates(mapper: Mapper) -> None:
    assert mapper.is_database_extension(".sqlite3")
    assert mapper.is_database_extension(".DBF")
    assert not mapper.is_database_extension(".hak")
    assert mapper.is_identifier_file(".nitins")
    assert mapper.is_identifier_file(".nitres")
    assert not mapper.is_identifier_file(".mod")


def test_optional_vs_mandatory_extension(mapper: Mapper) -> None:
    assert not mapper.is_optional_extension(".mod")  # mandatory
    assert mapper.is_optional_extension(".png")       # optional


def test_excluded_folder_and_file(mapper: Mapper) -> None:
    assert mapper.is_excluded_folder("__MACOSX")
    assert mapper.is_excluded_folder(".Mod Installer")
    assert not mapper.is_excluded_folder("hak")
    assert mapper.is_excluded_file("dc_genericdoors.ini")
    assert not mapper.is_excluded_file("world.mod")


def test_is_demo_mod(mapper: Mapper) -> None:
    assert mapper.is_demo_mod("demo.mod")
    assert mapper.is_demo_mod("Demo Adventure.mod")
    assert mapper.is_demo_mod("my test.mod")  # "test" substring
    assert not mapper.is_demo_mod("Rademon Keep.mod")  # contains 'demo'? no
    assert not mapper.is_demo_mod("demolition.mod")  # 'demo' embedded, not a word
    assert not mapper.is_demo_mod("hero.tga")  # not a .mod


def test_legal_folder(mapper: Mapper) -> None:
    assert mapper.is_legal_folder("override")
    assert mapper.is_legal_folder("hak")
    assert mapper.is_legal_folder("nwn")
    assert mapper.is_ee and mapper.is_legal_folder("ovr")  # EE-only
    assert not mapper.is_legal_folder("bogusfolder")


def test_ee_reclassifies_gui_shd() -> None:
    ee = Mapper(is_ee=True)
    nwn = Mapper(is_ee=False)
    assert ee.nwn_extensions[".gui"] == M.FOLDER_OVR
    assert nwn.nwn_extensions[".gui"] == M.FOLDER_OVERRIDE
    # But get_mapped_folder placement still uses ext_mapping (override) for both.
    assert ee.get_mapped_folder("mod/x/panel.gui") == M.FOLDER_OVERRIDE
