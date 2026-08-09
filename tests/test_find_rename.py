"""Tests for bulk find-and-rename over mod names (VB ModFindAndRename)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.game.find_rename import ModRenameSet, vb_replace
from vaultkeeper.ui.controller import ProfileController


# -- vb_replace (VB Strings.Replace count semantics) --------------------- #
def test_vb_replace_first_occurrence_only() -> None:
    # count=1 -> replace only the first match (VB MatchStart / ReplaceCount=1)
    assert vb_replace("aXbXc", "X", "Y", count=1, case_sensitive=True) == "aYbXc"


def test_vb_replace_all_occurrences() -> None:
    assert vb_replace("aXbXc", "X", "Y", count=-1, case_sensitive=True) == "aYbYc"


def test_vb_replace_case_insensitive() -> None:
    assert vb_replace("Foo foo", "foo", "bar", count=-1, case_sensitive=False) == "bar bar"


def test_vb_replace_case_sensitive_skips_mismatched_case() -> None:
    assert vb_replace("Foo foo", "foo", "bar", count=-1, case_sensitive=True) == "Foo bar"


def test_vb_replace_empty_find_is_noop() -> None:
    assert vb_replace("abc", "", "Y", count=-1, case_sensitive=True) == "abc"


# -- ModRenameSet find --------------------------------------------------- #
def _set(names: list[str], **kw: object) -> ModRenameSet:
    return ModRenameSet.from_names(names, **kw)  # type: ignore[arg-type]


def test_find_match_start_uses_startswith() -> None:
    s = _set(["Alpha Quest", "Beta Alpha", "Alpha Two"], match_start=True)
    found = s.find("Alpha")
    names = {s.entries[i].new_name for i in found}
    assert names == {"Alpha Quest", "Alpha Two"}  # "Beta Alpha" excluded


def test_find_contains_when_match_start_off() -> None:
    s = _set(["Alpha Quest", "Beta Alpha", "Gamma"], match_start=False)
    found = s.find("Alpha")
    names = {s.entries[i].new_name for i in found}
    assert names == {"Alpha Quest", "Beta Alpha"}


def test_find_blank_matches_nothing() -> None:
    s = _set(["Alpha", "Beta"])
    assert s.find("") == []
    assert s.found_count == 0


def test_find_case_insensitive_by_default() -> None:
    s = _set(["Alpha", "alphabet"], match_start=True, match_case=False)
    assert len(s.find("ALPHA")) == 2


def test_find_case_sensitive() -> None:
    s = _set(["Alpha", "alphabet"], match_start=True, match_case=True)
    found = s.find("Alpha")
    assert {s.entries[i].new_name for i in found} == {"Alpha"}


# -- replace ------------------------------------------------------------- #
def test_replace_all_prefix_rename() -> None:
    s = _set(["MyMod A", "MyMod B", "Other"], match_start=True)
    s.find("MyMod ")
    s.replace_all("Adventure ")
    assert s.renames == {"MyMod A": "Adventure A", "MyMod B": "Adventure B"}


def test_replace_all_only_first_occurrence_when_match_start() -> None:
    # Match start => ReplaceCount=1 => only the first "aa" becomes "b".
    s2 = _set(["aa foo aa"], match_start=True)
    s2.find("aa")  # startswith "aa" -> matches
    s2.replace_all("b")
    assert s2.entries[0].new_name == "b foo aa"


def test_replace_all_all_occurrences_when_not_match_start() -> None:
    s = _set(["x foo x bar x"], match_start=False)
    s.find("x")
    s.replace_all("Z")
    assert s.entries[0].new_name == "Z foo Z bar Z"


def test_replace_result_is_trimmed() -> None:
    s = _set(["  Alpha"], match_start=False)
    s.find("Alpha")
    s.replace_all("")  # remove "Alpha" -> "  " -> trimmed to ""
    # entry becomes blank current->"" is a change but blank names are for the UI to guard;
    # here just verify trimming happened.
    assert s.entries[0].new_name == ""


def test_duplicate_excluded_from_renames() -> None:
    # Renaming "Beta X" -> "Alpha" collides with existing "Alpha" => flagged, excluded.
    s = _set(["Alpha", "Beta X"], match_start=True)
    s.find("Beta X")
    s.replace_all("Alpha")
    assert s.duplicate_count == 1
    assert "Beta X" not in s.renames  # collision dropped
    assert s.renames == {}


def test_find_next_cycles_through_matches() -> None:
    s = _set(["Alpha One", "Alpha Two", "Alpha Three"], match_start=True)
    s.find("Alpha")
    # Windows-sorted: One, Three, Two -> indices 0,1,2 all match.
    first = s.find_next()
    second = s.find_next()
    third = s.find_next()
    fourth = s.find_next()  # cycles back
    assert [first, second, third] == [0, 1, 2]
    assert fourth == 0


def test_find_next_none_when_no_match() -> None:
    s = _set(["Alpha"], match_start=True)
    s.find("zzz")
    assert s.find_next() is None


def test_undo_one_reverts_single_entry() -> None:
    s = _set(["MyMod A", "MyMod B"], match_start=True)
    s.find("MyMod ")
    s.replace_all("New ")
    assert s.change_count == 2
    s.undo_one(0)
    assert s.change_count == 1


def test_reset_reverts_all() -> None:
    s = _set(["MyMod A", "MyMod B"], match_start=True)
    s.find("MyMod ")
    s.replace_all("New ")
    assert s.change_count == 2
    s.reset()
    assert s.change_count == 0
    assert s.renames == {}


# -- controller integration ---------------------------------------------- #
def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _make_mod(controller: ProfileController, tmp_path: Path, name: str) -> None:
    controller.create_mod(name)
    payload = (
        tmp_path / "Profiles" / "P" / name / C.MOD_INSTALLER_DIR / "override" / "a.tga"
    )
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_bytes(b"TGADATA")


def test_mod_rename_set_seeds_from_profile(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _make_mod(controller, tmp_path, "Zeta Mod")
    _make_mod(controller, tmp_path, "Alpha Mod")
    s = controller.mod_rename_set()
    # Windows-sorted, group rows excluded.
    assert [e.current_name for e in s.entries] == ["Alpha Mod", "Zeta Mod"]


def test_apply_mod_renames_renames_folders(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _make_mod(controller, tmp_path, "Old One")
    _make_mod(controller, tmp_path, "Old Two")

    report = controller.apply_mod_renames({"Old One": "New One", "Old Two": "New Two"})
    assert set(report["renamed"]) == {"New One", "New Two"}
    assert report["failed"] == []

    assert "New One" in controller.pd.mod_keys
    assert "Old One" not in controller.pd.mod_keys
    assert (tmp_path / "Profiles" / "P" / "New One").is_dir()
    assert not (tmp_path / "Profiles" / "P" / "Old One").exists()


def test_apply_mod_renames_end_to_end_find_replace(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _make_mod(controller, tmp_path, "WIP Alpha")
    _make_mod(controller, tmp_path, "WIP Beta")
    _make_mod(controller, tmp_path, "Keep Me")

    s = controller.mod_rename_set()
    s.find("WIP ")
    s.replace_all("Done ")
    controller.apply_mod_renames(s.renames)

    assert "Done Alpha" in controller.pd.mod_keys
    assert "Done Beta" in controller.pd.mod_keys
    assert "Keep Me" in controller.pd.mod_keys
    assert "WIP Alpha" not in controller.pd.mod_keys


# -- dialog -------------------------------------------------------------- #
def test_dialog_bulk_rename_flow(qtbot, tmp_path: Path, monkeypatch) -> None:
    from vaultkeeper.ui.dialogs import find_and_rename as far
    from vaultkeeper.ui.dialogs.find_and_rename import FindAndRenameDialog

    monkeypatch.setattr(far.QMessageBox, "information", lambda *a, **k: None)
    controller = _controller(tmp_path)
    _make_mod(controller, tmp_path, "WIP Alpha")
    _make_mod(controller, tmp_path, "WIP Beta")
    _make_mod(controller, tmp_path, "Keep Me")

    dlg = FindAndRenameDialog(controller)
    qtbot.addWidget(dlg)
    # List shows all three mod names, windows-sorted.
    assert dlg._list.count() == 3

    dlg._find.setText("WIP ")
    dlg._replace.setText("Done ")
    dlg._replace_all()

    # Two entries now changed; Apply enabled.
    assert dlg._model.change_count == 2
    assert dlg._apply_btn.isEnabled()

    dlg._apply()
    assert "Done Alpha" in controller.pd.mod_keys
    assert "WIP Alpha" not in controller.pd.mod_keys


def test_dialog_duplicate_is_flagged_and_not_applied(qtbot, tmp_path: Path) -> None:
    from vaultkeeper.ui.dialogs.find_and_rename import FindAndRenameDialog

    controller = _controller(tmp_path)
    _make_mod(controller, tmp_path, "Alpha")
    _make_mod(controller, tmp_path, "Beta")

    dlg = FindAndRenameDialog(controller)
    qtbot.addWidget(dlg)
    # Rename "Beta" -> "Alpha" (collides with existing Alpha).
    dlg._find.setText("Beta")
    dlg._replace.setText("Alpha")
    dlg._replace_all()

    assert dlg._model.duplicate_count == 1
    assert dlg._model.renames == {}
    assert not dlg._apply_btn.isEnabled()


def test_double_clicking_a_mod_loads_its_name_into_both_boxes(qtbot, tmp_path, monkeypatch):
    """VB LvMods_MouseDoubleClick — the quickest way to rename one thing, which
    is what a find-and-replace over names is usually being used for."""
    from vaultkeeper.ui.dialogs import find_and_rename as far
    from vaultkeeper.ui.dialogs.find_and_rename import FindAndRenameDialog

    monkeypatch.setattr(far.QMessageBox, "information", lambda *a, **k: None)
    controller = _controller(tmp_path)
    _make_mod(controller, tmp_path, "WIP Alpha")

    dlg = FindAndRenameDialog(controller)
    qtbot.addWidget(dlg)
    dlg._on_mod_double_clicked(dlg._list.item(0))
    assert dlg._find.text() == "WIP Alpha"
    assert dlg._replace.text() == "WIP Alpha"


def test_double_clicking_an_empty_row_changes_nothing(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QListWidgetItem

    from vaultkeeper.ui.dialogs import find_and_rename as far
    from vaultkeeper.ui.dialogs.find_and_rename import FindAndRenameDialog

    monkeypatch.setattr(far.QMessageBox, "information", lambda *a, **k: None)
    dlg = FindAndRenameDialog(_controller(tmp_path))
    qtbot.addWidget(dlg)
    dlg._find.setText("keep")
    dlg._on_mod_double_clicked(QListWidgetItem("   "))
    assert dlg._find.text() == "keep"
