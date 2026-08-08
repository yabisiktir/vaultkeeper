"""Character Restorers — saving the character you played a mod with.

The judgement is in the grouping: NWN numbers a character's files, so
Aribeth.bic / Aribeth1.bic / Aribeth2.bic are one character and must become one
restorer, while two different names must never be merged into one.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.core.file_key import FileKeyInfo
from vaultkeeper.game.character_restorer import (
    base_name,
    group_characters,
    restorer_name,
)
from vaultkeeper.ui.controller import ProfileController


class TestBaseName:
    def test_the_trailing_number_is_the_save_slot_not_the_character(self):
        assert base_name("Aribeth2.bic") == "Aribeth"

    def test_an_unnumbered_character(self):
        assert base_name("Aribeth.bic") == "Aribeth"

    def test_digits_inside_the_name_are_kept(self):
        assert base_name("Agent47Smith.bic") == "Agent47Smith"

    def test_a_name_that_is_all_digits_keeps_them(self):
        """Stripping would leave nothing to call the restorer."""
        assert base_name("12345.bic") == "12345"

    def test_a_name_with_no_extension(self):
        assert base_name("Aribeth3") == "Aribeth"


def _key(filename: str) -> FileKeyInfo:
    return FileKeyInfo.installed("localvault", filename)


class TestGrouping:
    def test_one_character_across_several_slots_is_one_restorer(self):
        keys = [_key(n) for n in ("Aribeth.bic", "Aribeth1.bic", "Aribeth2.bic")]
        groups = group_characters(keys)
        assert [g.name for g in groups] == ["Aribeth"]
        assert groups[0].count == 3

    def test_two_characters_are_never_merged(self):
        keys = [_key("Aribeth.bic"), _key("Boddyknock1.bic")]
        assert [g.name for g in group_characters(keys)] == ["Aribeth", "Boddyknock"]

    def test_the_order_is_stable_and_readable(self):
        keys = [_key("zed.bic"), _key("Aribeth.bic"), _key("miri.bic")]
        assert [g.name for g in group_characters(keys)] == ["Aribeth", "miri", "zed"]

    def test_nothing_unowned_is_nothing_to_do(self):
        assert group_characters([]) == []


class TestRestorerName:
    def test_punctuation_prefixes_glue_on(self):
        """"-Aribeth" is the original's own convention."""
        assert restorer_name("-", "Aribeth") == "-Aribeth"

    def test_word_prefixes_get_a_space(self):
        assert restorer_name("Char", "Aribeth") == "Char Aribeth"

    def test_no_prefix_is_just_the_name(self):
        assert restorer_name("", "Aribeth") == "Aribeth"
        assert restorer_name("   ", "Aribeth") == "Aribeth"


# -- the controller ------------------------------------------------------------- #
def _controller(tmp_path: Path, characters=()) -> ProfileController:
    """A profile whose game holds ``characters`` that no mod installed."""
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    user = tmp_path / "user"
    (user / "localvault").mkdir(parents=True)
    for name in characters:
        (user / "localvault" / name).write_bytes(b"BIC V3.28" + name.encode())
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=user,
    )
    controller.rescan_installed_state()
    return controller


def test_characters_the_game_holds_are_found(tmp_path):
    controller = _controller(tmp_path, ["Aribeth.bic", "Aribeth1.bic", "Boddyknock.bic"])
    groups = controller.unowned_characters()
    assert [(g.name, g.count) for g in groups] == [("Aribeth", 2), ("Boddyknock", 1)]


def test_a_restorer_copies_the_files_and_owns_them(tmp_path):
    controller = _controller(tmp_path, ["Aribeth.bic", "Aribeth1.bic"])
    groups = controller.unowned_characters()
    result = controller.create_character_restorer("-Aribeth", groups[0].files)
    assert result["ok"] and result["files"] == 2

    md = controller.pd.mod_item("-Aribeth")
    assert md is not None
    assert md.group == C.CHARACTER_RESTORER_GROUP
    assert md.is_restorer()
    payload = tmp_path / "Profiles" / "P" / "-Aribeth" / C.MOD_INSTALLER_DIR
    assert (payload / "localvault" / "Aribeth.bic").is_file()


def test_the_characters_are_left_in_the_game(tmp_path):
    """A restorer is a backup; it must never move anything out of the game."""
    controller = _controller(tmp_path, ["Aribeth.bic"])
    groups = controller.unowned_characters()
    controller.create_character_restorer("-Aribeth", groups[0].files)
    assert (tmp_path / "user" / "localvault" / "Aribeth.bic").is_file()


def test_an_existing_name_is_refused(tmp_path):
    controller = _controller(tmp_path, ["Aribeth.bic"])
    groups = controller.unowned_characters()
    controller.create_character_restorer("-Aribeth", groups[0].files)
    again = controller.create_character_restorer("-Aribeth", groups[0].files)
    assert not again["ok"] and "already exists" in again["message"]


def test_an_unnamed_restorer_is_refused(tmp_path):
    controller = _controller(tmp_path, ["Aribeth.bic"])
    groups = controller.unowned_characters()
    assert not controller.create_character_restorer("  ", groups[0].files)["ok"]


class TestAutomatic:
    def test_one_character_is_named_after_the_mod_just_played(self, tmp_path):
        controller = _controller(tmp_path, ["Aribeth.bic", "Aribeth1.bic"])
        result = controller.auto_character_restorers("Aielund Saga")
        assert result["created"] == 1
        assert controller.pd.mod_item("-Aielund Saga") is not None

    def test_several_characters_are_left_for_a_person_to_sort_out(self, tmp_path):
        """Which build belongs to which mod is not something to guess."""
        controller = _controller(tmp_path, ["Aribeth.bic", "Boddyknock.bic"])
        result = controller.auto_character_restorers("Aielund Saga")
        assert result["created"] == 0 and result["pending"] == 2

    def test_nothing_unowned_does_nothing(self, tmp_path):
        assert _controller(tmp_path).auto_character_restorers("X")["created"] == 0

    def test_it_does_not_make_the_same_restorer_twice(self, tmp_path):
        controller = _controller(tmp_path, ["Aribeth.bic"])
        assert controller.auto_character_restorers("Aielund Saga")["created"] == 1
        assert controller.auto_character_restorers("Aielund Saga")["created"] == 0


def test_the_dialog_offers_every_character_ticked(qtbot, tmp_path):
    from vaultkeeper.ui.dialogs.character_restorer import CharacterRestorerDialog

    controller = _controller(tmp_path, ["Aribeth.bic", "Boddyknock.bic"])
    dlg = CharacterRestorerDialog(controller.unowned_characters(), "-")
    qtbot.addWidget(dlg)
    assert [name for name, _ in dlg.chosen()] == ["-Aribeth", "-Boddyknock"]


def test_unticking_one_leaves_it_out(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    from vaultkeeper.ui.dialogs.character_restorer import CharacterRestorerDialog

    controller = _controller(tmp_path, ["Aribeth.bic", "Boddyknock.bic"])
    dlg = CharacterRestorerDialog(controller.unowned_characters(), "-")
    qtbot.addWidget(dlg)
    dlg.table.topLevelItem(0).setCheckState(0, Qt.CheckState.Unchecked)
    assert [name for name, _ in dlg.chosen()] == ["-Boddyknock"]


def test_a_renamed_row_is_used(qtbot, tmp_path):
    from vaultkeeper.ui.dialogs.character_restorer import CharacterRestorerDialog

    controller = _controller(tmp_path, ["Aribeth.bic"])
    dlg = CharacterRestorerDialog(controller.unowned_characters(), "-")
    qtbot.addWidget(dlg)
    dlg.table.topLevelItem(0).setText(0, "My Paladin")
    assert [name for name, _ in dlg.chosen()] == ["My Paladin"]
