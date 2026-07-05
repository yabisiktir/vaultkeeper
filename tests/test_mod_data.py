"""Tests for ModData: identity, predicates, and the SetModState machine."""

from __future__ import annotations

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.core.mod_data import ModData
from vaultkeeper.core.state import GroupStatus, State, Weapon


def _mod(name: str = "Cool Mod", group: str = "Group") -> ModData:
    return ModData(group=group, mod_name=name)


# --- identity ------------------------------------------------------------- #
def test_group_vs_mod_item() -> None:
    grp = ModData(group="Group")  # empty mod_name -> group row
    assert grp.is_group_item and not grp.is_not_group_item
    mod = _mod()
    assert mod.is_not_group_item and not mod.is_group_item


def test_hidden_group() -> None:
    assert ModData(group=C.GROUP_INSTALLED).is_hidden_group
    assert ModData(group=C.GROUP_NONE).is_hidden_group
    assert not ModData(group="Normal").is_hidden_group


def test_level_null_coercion() -> None:
    md = _mod()
    md.level_start = 0  # 0 means "not specified" -> NULL_VALUE
    assert md.level_start == C.NULL_VALUE
    md.level_end = 5
    assert md.level_end == 5
    md.level_end = 0
    assert md.level_end == C.NULL_VALUE


def test_steam_managed() -> None:
    md = _mod()
    assert not md.is_steam_managed
    md.workshop_id = "12345"
    assert md.is_steam_managed


# --- file predicates ------------------------------------------------------ #
def test_has_mod_file() -> None:
    md = _mod()
    assert not md.has_mod_file
    md.files.append(FileKeyInfo("Group", "Cool Mod", C.MOD_FOLDER, "world.mod"))
    assert md.has_mod_file


def test_is_installer_and_restorer() -> None:
    md = _mod("Adventure")
    assert not md.is_installer() and not md.is_restorer()
    md.files.append(FileKeyInfo("Group", "Adventure", C.MOD_NIT_DIR, "Adventure.nitins"))
    assert md.is_installer() and not md.is_restorer()
    md2 = _mod("Restore")
    md2.files.append(FileKeyInfo("Group", "Restore", C.MOD_NIT_DIR, "Restore.nitres"))
    assert md2.is_restorer() and not md2.is_installer()


def test_is_mod_identifier_file() -> None:
    md = _mod("Adventure")
    idf = FileKeyInfo("Group", "Adventure", C.MOD_NIT_DIR, "Adventure.nitins")
    other = FileKeyInfo("Group", "Adventure", "hak", "a.hak")
    assert md.is_mod_identifier_file(idf)
    assert not md.is_mod_identifier_file(other)


def test_file_key_index() -> None:
    md = _mod()
    fk = FileKeyInfo("Group", "Cool Mod", "hak", "a.hak")
    assert md.file_key_index(fk) == -1
    md.files.append(fk)
    assert md.file_key_index(FileKeyInfo("Group", "Cool Mod", "hak", "a.hak")) == 0


# --- SetModState machine -------------------------------------------------- #
def _lookup(states: dict[str, State]):
    def fn(fk: FileKeyInfo) -> State | None:
        return states.get(fk.filename)
    return fn


def _mod_with_files(*filenames: str) -> ModData:
    md = _mod()
    for name in filenames:
        md.files.append(FileKeyInfo("Group", "Cool Mod", "hak", name))
    return md


def test_state_no_files() -> None:
    md = _mod()
    md.set_mod_state(_lookup({}), has_mod_installer=False, total_file_count=0)
    assert md.mod_state == State.NONE
    md.set_mod_state(_lookup({}), has_mod_installer=True, total_file_count=0)
    assert md.mod_state == State.NOT_INSTALLED


def test_state_all_installed() -> None:
    md = _mod_with_files("a.hak", "b.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.INSTALLED, "b.hak": State.INSTALLED}),
        has_mod_installer=True,
        total_file_count=2,
    )
    assert md.mod_state == State.INSTALLED
    assert md.installed


def test_state_some_installed() -> None:
    md = _mod_with_files("a.hak", "b.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.INSTALLED, "b.hak": State.NOT_INSTALLED}),
        has_mod_installer=True,
        total_file_count=2,
    )
    assert md.mod_state == State.SOME_INSTALLED
    assert not md.installed  # SomeInstalled(2) is not > InstallState(10)


def test_state_not_installed() -> None:
    md = _mod_with_files("a.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.NOT_INSTALLED}), has_mod_installer=True, total_file_count=1
    )
    assert md.mod_state == State.NOT_INSTALLED


def test_state_overridden_variants() -> None:
    # All overridden, override_count == total -> Overridden
    md = _mod_with_files("a.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.OVERRIDDEN}), has_mod_installer=True, total_file_count=1
    )
    assert md.mod_state == State.OVERRIDDEN

    # Overridden + some not installed -> SomeAndOverridden
    md = _mod_with_files("a.hak", "b.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.OVERRIDDEN, "b.hak": State.NOT_INSTALLED}),
        has_mod_installer=True,
        total_file_count=5,
    )
    assert md.mod_state == State.SOME_AND_OVERRIDDEN

    # Overridden, none not-installed, override_count < total -> InstalledAndOverridden
    md = _mod_with_files("a.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.OVERRIDDEN}), has_mod_installer=True, total_file_count=5
    )
    assert md.mod_state == State.INSTALLED_AND_OVERRIDDEN


def test_state_match_override_variants() -> None:
    md = _mod_with_files("a.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.MATCH_OVERRIDE}), has_mod_installer=True, total_file_count=1
    )
    assert md.mod_state == State.MATCH_OVERRIDE

    md = _mod_with_files("a.hak", "b.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.MATCH_OVERRIDE, "b.hak": State.NOT_INSTALLED}),
        has_mod_installer=True,
        total_file_count=2,
    )
    assert md.mod_state == State.SOME_AND_MATCH


def test_state_patch_ini_follows_mod_state() -> None:
    # An overridden nwnpatch.ini counts as installed when the mod is already
    # installed, so it doesn't drag an installed mod into an overridden state.
    md = _mod()
    md.files.append(FileKeyInfo("Group", "Cool Mod", "nwn", C.PATCH_INI_FILE))
    md.mod_state = State.INSTALLED  # already installed
    md.set_mod_state(
        _lookup({C.PATCH_INI_FILE: State.OVERRIDDEN}),
        has_mod_installer=True,
        total_file_count=1,
    )
    assert md.mod_state == State.INSTALLED


def test_state_skips_unknown_file() -> None:
    md = _mod_with_files("a.hak", "missing.hak")
    md.set_mod_state(
        _lookup({"a.hak": State.INSTALLED}),  # missing.hak -> None, skipped
        has_mod_installer=True,
        total_file_count=2,
    )
    assert md.mod_state == State.INSTALLED


# --- clone ---------------------------------------------------------------- #
def test_clone() -> None:
    md = _mod()
    md.best_weapon = Weapon.KATANA
    md.rating = md.rating  # keep default
    md.workshop_id = "9"
    md.group_state = GroupStatus.COLLAPSED
    md.files.append(FileKeyInfo("Group", "Cool Mod", "hak", "a.hak"))
    md.dependencies.append("Other Mod")
    c = md.clone()
    assert c is not md
    assert c.best_weapon == Weapon.KATANA
    assert c.workshop_id == "9"
    assert c.group_state == GroupStatus.COLLAPSED
    assert c.files == md.files and c.files is not md.files
    assert c.dependencies == ["Other Mod"] and c.dependencies is not md.dependencies
