"""Tests for ChangeData / InfoFiles / InfoMods accumulator mechanics."""

from __future__ import annotations

from vaultkeeper.core.change_data import ChangeData, InfoFiles, InfoMods
from vaultkeeper.core.file_key import FileKeyInfo


def _fk(name: str, mod: str = "Mod") -> FileKeyInfo:
    return FileKeyInfo("G", mod, "hak", name)


# --- InfoFiles ------------------------------------------------------------ #
def test_added_updates_update_list_and_dedups() -> None:
    inf = InfoFiles()
    inf.added(_fk("a.hak"))
    inf.added(_fk("a.hak"))  # dup ignored (case-insensitive identity)
    inf.added(FileKeyInfo("G", "Mod", "hak", "A.HAK"))  # same identity -> dup
    assert inf.adds == 1
    assert len(inf.update_list) == 1
    assert inf.changes_detected


def test_added_removes_from_removed_list() -> None:
    inf = InfoFiles()
    inf.removed(_fk("a.hak"))
    assert inf.removes == 1
    inf.added(_fk("a.hak"))  # re-adding clears the pending removal
    assert inf.removes == 0


def test_changed_tracks_update_list() -> None:
    inf = InfoFiles()
    inf.changed(_fk("a.hak"))
    assert inf.changes == 1
    assert len(inf.update_list) == 1


def test_update_states_and_illegal() -> None:
    inf = InfoFiles()
    assert not inf.update_states
    inf.renamed(_fk("a.hak"))
    assert inf.update_states  # rename counts
    inf.illegal_files.append(_fk("bad.exe"))
    assert inf.illegal_items


def test_infofiles_clone_is_independent() -> None:
    inf = InfoFiles()
    inf.added(_fk("a.hak"))
    c = inf.clone()
    c.added(_fk("b.hak"))
    assert inf.adds == 1 and c.adds == 2


# --- InfoMods (case-insensitive names) ------------------------------------ #
def test_mods_added_dedup_case_insensitive() -> None:
    im = InfoMods()
    im.added("Cool Mod")
    im.added("cool mod")
    assert im.adds == 1


def test_mods_added_clears_removed() -> None:
    im = InfoMods()
    im.removed("Mod A")
    assert im.removes == 1
    im.added("mod a")  # case-insensitive removal
    assert im.removes == 0


def test_mods_affected_dedup() -> None:
    im = InfoMods()
    im.affected("X")
    im.affected("x")
    assert im.affecteds == 1
    assert InfoMods.name_exists(im.affected_list, "X")


# --- ChangeData aggregate + save/merge/restore ---------------------------- #
def test_reset_and_detected() -> None:
    cd = ChangeData()
    assert not cd.detected
    cd.file.added(_fk("a.hak"))
    assert cd.detected and cd.update_checksums
    cd.reset_changes()
    assert not cd.detected


def test_save_and_restore_roundtrip() -> None:
    cd = ChangeData()
    cd.file.added(_fk("a.hak"))
    cd.mods.affected("Mod")
    cd.save_info()
    # Mutate after saving.
    cd.file.added(_fk("b.hak"))
    cd.mods.affected("Other")
    # Restore -> back to exactly the saved snapshot.
    cd.restore_saved_info()
    assert cd.file.adds == 1
    assert [str(k) for k in cd.file.added_list] == [str(_fk("a.hak"))]
    assert cd.mods.affected_list == ["Mod"]


def test_merge_keeps_current_and_saved() -> None:
    cd = ChangeData()
    cd.file.added(_fk("a.hak"))
    cd.save_info()
    cd.file.added(_fk("b.hak"))  # current, not in snapshot
    cd.merge_saved_info()
    names = {k.filename for k in cd.file.added_list}
    assert names == {"a.hak", "b.hak"}
    # merge clears the update lists (checksums already handled).
    assert cd.file.update_list == []


def test_merge_dedups_orphaned_notes() -> None:
    cd = ChangeData()
    cd.orphaned_mod_notes.append("note1")
    cd.save_info()
    cd.orphaned_mod_notes.append("note1")  # duplicate after save
    cd.orphaned_mod_notes.append("note2")
    cd.merge_saved_info()
    assert cd.orphaned_mod_notes == ["note1", "note2"]


def test_clone_independent() -> None:
    cd = ChangeData()
    cd.file.added(_fk("a.hak"))
    c = cd.clone()
    c.file.added(_fk("b.hak"))
    assert cd.file.adds == 1 and c.file.adds == 2
