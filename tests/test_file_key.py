"""Tests for FileKeyInfo identity, derived keys, predicates and ordering."""

from __future__ import annotations

from functools import cmp_to_key

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo


# --- derived keys --------------------------------------------------------- #
def test_derived_keys() -> None:
    fk = FileKeyInfo("MyGroup", "Cool Mod", "hak", "stuff.hak")
    assert fk.file_key == "hak\\stuff.hak"
    assert fk.qualifier == "MyGroup\\Cool Mod"
    assert fk.full_key == "MyGroup\\Cool Mod\\hak\\stuff.hak"
    assert str(fk) == fk.full_key


def test_installed_factory_uses_sentinels() -> None:
    fk = FileKeyInfo.installed("hak", "core.hak")
    assert fk.group == C.GROUP_INSTALLED == "......000"
    assert fk.mod_name == C.INSTALLED_FILES_LABEL == "Installed Files"
    assert fk.is_not_mod_file and not fk.is_mod_file


def test_from_key_splits_folder_and_file() -> None:
    fk = FileKeyInfo.mod_file("G", "M", "hak\\thing.hak")
    assert fk.folder == "hak"
    assert fk.filename == "thing.hak"


def test_forward_slashes_normalised() -> None:
    fk = FileKeyInfo.installed_from_key("override/foo.tga")
    assert fk.folder == "override"
    assert fk.filename == "foo.tga"


def test_root_folder_normalisation() -> None:
    # A file in the game root records folder as the "nwn" marker.
    fk = FileKeyInfo(
        "G", "M", "Neverwinter Nights", "nwn.ini", root_folder_name="Neverwinter Nights"
    )
    assert fk.folder == C.MOD_ROOT_FOLDER == "nwn"
    # Without the hint, no normalisation happens.
    fk2 = FileKeyInfo("G", "M", "Neverwinter Nights", "nwn.ini")
    assert fk2.folder == "Neverwinter Nights"


def test_installed_key_strips_identity() -> None:
    fk = FileKeyInfo("Grp", "Mod A", "hak", "a.hak")
    ik = fk.installed_key
    assert ik.group == C.GROUP_INSTALLED
    assert ik.mod_name == C.INSTALLED_FILES_LABEL
    assert ik.folder == "hak" and ik.filename == "a.hak"


def test_full_key_roundtrip() -> None:
    fk = FileKeyInfo("Grp", "Mod A", "hak", "a.hak")
    assert FileKeyInfo.from_full_key(fk.full_key) == fk


# --- predicates ----------------------------------------------------------- #
def test_extension() -> None:
    assert FileKeyInfo("g", "m", "hak", "a.HAK").extension == ".HAK"
    assert FileKeyInfo("g", "m", "d", "noext").extension == ""


def test_mod_extension() -> None:
    assert FileKeyInfo("g", "m", "modules", "world.mod").is_mod_extension
    assert FileKeyInfo("g", "m", "modules", "old.NWM").is_mod_extension
    assert not FileKeyInfo("g", "m", "hak", "a.hak").is_mod_extension


def test_identifier_keys() -> None:
    ins = FileKeyInfo("g", "m", C.MOD_NIT_DIR, "id.nitins")
    res = FileKeyInfo("g", "m", C.MOD_NIT_DIR, "id.nitres")
    assert ins.is_installer_key and ins.is_identifier_key and not ins.is_restorer_key
    assert res.is_restorer_key and res.is_identifier_key and not res.is_installer_key
    assert not FileKeyInfo("g", "m", "hak", "a.nitins").is_installer_key  # wrong folder


# --- identity: case-insensitive equality + hashing ------------------------ #
def test_equality_is_case_insensitive() -> None:
    a = FileKeyInfo("Grp", "Mod", "Hak", "File.Hak")
    b = FileKeyInfo("grp", "mod", "hak", "file.hak")
    assert a == b
    assert hash(a) == hash(b)


def test_usable_as_dict_key_case_insensitively() -> None:
    d: dict[FileKeyInfo, int] = {}
    d[FileKeyInfo("G", "M", "hak", "a.hak")] = 1
    d[FileKeyInfo("g", "m", "HAK", "A.HAK")] = 2  # same identity, overwrites
    assert len(d) == 1
    assert d[FileKeyInfo("G", "M", "hak", "a.hak")] == 2


def test_inequality_when_different() -> None:
    assert FileKeyInfo("G", "M", "hak", "a.hak") != FileKeyInfo("G", "M", "hak", "b.hak")
    assert FileKeyInfo("G", "M1", "hak", "a.hak") != FileKeyInfo("G", "M2", "hak", "a.hak")


# --- ordering: winner selection ------------------------------------------ #
def test_comparer_orders_by_qualifier_then_filekey() -> None:
    # Same file present in two mods; winner = greatest qualifier.
    low = FileKeyInfo("Group", "Mod A", "hak", "shared.hak")
    high = FileKeyInfo("Group", "Mod B", "hak", "shared.hak")
    assert FileKeyInfo.comparer(low, high) < 0
    conflicts = [high, low]
    ordered = sorted(conflicts, key=cmp_to_key(FileKeyInfo.comparer))
    # Install semantics: last in sorted list wins.
    assert ordered[-1] is high
    # Uninstall semantics: reversed, take index 0 -> same winner.
    assert sorted(conflicts, key=cmp_to_key(FileKeyInfo.comparer), reverse=True)[0] is high


def test_comparer_numeric_mod_names() -> None:
    # Numeric-aware: "Mod 10" must sort after "Mod 2" -> it wins a conflict.
    m2 = FileKeyInfo("G", "Mod 2", "hak", "x.hak")
    m10 = FileKeyInfo("G", "Mod 10", "hak", "x.hak")
    winner = sorted([m10, m2], key=cmp_to_key(FileKeyInfo.comparer))[-1]
    assert winner is m10


def test_compare_to_uses_full_key() -> None:
    a = FileKeyInfo("A", "m", "hak", "f.hak")
    b = FileKeyInfo("B", "m", "hak", "f.hak")
    assert a.compare_to(b) < 0
    assert b.compare_to(a) > 0
    assert a.compare_to(FileKeyInfo("a", "m", "hak", "f.hak")) == 0
