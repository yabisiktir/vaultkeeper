"""Spotting the previous version of what was just downloaded.

Everything here is a *suggestion*. The tests that matter most are the ones
asserting what is **not** offered, and what is offered unticked: a name-matching
rule cannot tell two versions of a mod from two halves of a set, and the cost of
being wrong is a download that may no longer exist anywhere.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.core import constants as C
from vaultkeeper.vault.old_downloads import date_stem, superseded, version_stem


class TestVersionStem:
    def test_a_trailing_version_is_removed(self):
        assert version_stem("mymodule_1_2.7z") == "mymodule"

    def test_a_v_prefixed_version_is_removed(self):
        assert version_stem("mymodule_v1_2.7z") == "mymodule"

    def test_hyphens_work_as_well_as_underscores(self):
        assert version_stem("my-module-2-1.rar") == "my-module"

    def test_a_dotted_version_part_is_still_a_version(self):
        assert version_stem("aielund_v3.01.zip") == "aielund"

    def test_a_name_with_no_version_comes_back_whole(self):
        assert version_stem("almraiven.rar") == "almraiven"

    def test_a_name_that_is_all_version_comes_back_whole(self):
        assert version_stem("1_2_3.7z") == "1_2_3"

    def test_a_stem_too_short_to_match_on_is_rejected(self):
        """"ab" would match half the folder, so the whole name is used instead."""
        assert version_stem("ab_1_2_3_4.7z") == "ab_1_2_3_4"

    def test_ver_is_stripped_before_v(self):
        """Getting the order wrong turns "ver1" into "er1", which is not a version."""
        assert version_stem("mymodule_ver1.7z") == "mymodule"


class TestDateStem:
    def test_a_plain_date_is_removed(self):
        assert date_stem("mymodule_20250104.7z") == "mymodule"

    def test_a_hyphenated_date_is_removed(self):
        assert date_stem("mymodule-2025-01-04.7z") == "mymodule"

    def test_a_name_without_a_date_has_no_date_stem(self):
        assert date_stem("mymodule_v1_2.7z") == ""

    def test_an_eight_digit_number_that_is_not_a_date_is_not_one(self):
        """A workshop id is eight digits and means nothing of the kind."""
        assert date_stem("workshop_99999999.7z") == ""


def _paths(tmp_path: Path, *names: str) -> list[Path]:
    made = []
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        made.append(target)
    return made


class TestSuperseded:
    def test_the_previous_version_is_offered_ticked(self, tmp_path):
        existing = _paths(tmp_path, "mymodule_1_1.7z")
        found = superseded(existing, ["mymodule_1_2.7z"])
        assert [(o.name, o.suggested) for o in found] == [("mymodule_1_1.7z", True)]

    def test_a_previous_dated_release_is_offered_ticked(self, tmp_path):
        existing = _paths(tmp_path, "mymodule_20250104.7z")
        found = superseded(existing, ["mymodule_20260214.7z"])
        assert [(o.name, o.suggested) for o in found] == [("mymodule_20250104.7z", True)]

    def test_the_file_being_downloaded_again_is_never_offered(self, tmp_path):
        """It is about to be overwritten, not superseded."""
        existing = _paths(tmp_path, "mymodule_1_2.7z")
        assert superseded(existing, ["mymodule_1_2.7z"]) == []

    def test_an_unrelated_archive_is_offered_unticked(self, tmp_path):
        """Offered because it may be wanted gone; unticked because nothing says so."""
        existing = _paths(tmp_path, "something_else.zip")
        found = superseded(existing, ["mymodule_1_2.7z"])
        assert [(o.name, o.suggested) for o in found] == [("something_else.zip", False)]

    def test_a_different_archive_format_is_still_in_scope(self, tmp_path):
        """A project that shipped .rar last year and .7z this year is one project."""
        existing = _paths(tmp_path, "mymodule_1_1.rar")
        assert superseded(existing, ["mymodule_1_2.7z"])[0].suggested

    def test_a_file_of_an_unrelated_kind_is_left_out(self, tmp_path):
        existing = _paths(tmp_path, "readme.txt")
        assert superseded(existing, ["mymodule_1_2.7z"]) == []

    def test_kept_copies_are_never_touched(self, tmp_path):
        existing = _paths(
            tmp_path,
            f"{C.HISTORY_DIR}/mymodule_1_1.7z",
            f"{C.PUBLISHED_DIR}/mymodule_1_0.7z",
        )
        assert superseded(existing, ["mymodule_1_2.7z"]) == []

    def test_the_other_half_of_a_set_is_not_ticked_off_as_old(self, tmp_path):
        """cep_3.1.4 part 1 and part 2 are one download, not two versions."""
        existing = _paths(tmp_path, "cep_3.1.4_-_part_1.7z")
        found = superseded(existing, ["cep_3.1.4_-_part_1.7z", "cep_3.1.4_-_part_2.7z"])
        assert found == []

    def test_suggestions_sort_ahead_of_the_rest(self, tmp_path):
        existing = _paths(tmp_path, "zzz_other.7z", "mymodule_1_1.7z")
        found = superseded(existing, ["mymodule_1_2.7z"])
        assert [o.name for o in found] == ["mymodule_1_1.7z", "zzz_other.7z"]

    def test_nothing_downloaded_means_nothing_superseded(self, tmp_path):
        assert superseded(_paths(tmp_path, "a.7z"), []) == []


# -- the controller and the dialog --------------------------------------------- #
def _controller(tmp_path):
    from vaultkeeper.ui.controller import ProfileController

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _downloads(tmp_path, mod: str, *names: str) -> Path:
    folder = tmp_path / "Profiles" / "P" / mod / C.DOWNLOADS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"x" * 16)
    return folder


def test_the_controller_finds_the_previous_version(tmp_path):
    ctrl = _controller(tmp_path)
    ctrl.create_mod("My Mod")
    _downloads(tmp_path, "My Mod", "mymodule_1_1.7z", "mymodule_1_2.7z")
    old = ctrl.superseded_downloads("My Mod", ["mymodule_1_2.7z"])
    assert [(o.name, o.suggested) for o in old] == [("mymodule_1_1.7z", True)]


def test_moving_to_history_keeps_the_file(tmp_path):
    ctrl = _controller(tmp_path)
    ctrl.create_mod("My Mod")
    folder = _downloads(tmp_path, "My Mod", "mymodule_1_1.7z")
    result = ctrl.remove_old_downloads([folder / "mymodule_1_1.7z"], to_history=True)
    assert result["ok"] and result["moved"] == 1
    kept = tmp_path / "Profiles" / "P" / "My Mod" / C.HISTORY_DIR / "mymodule_1_1.7z"
    assert kept.is_file()
    assert not (folder / "mymodule_1_1.7z").exists()


def test_a_name_already_in_history_does_not_overwrite_it(tmp_path):
    ctrl = _controller(tmp_path)
    ctrl.create_mod("My Mod")
    history = tmp_path / "Profiles" / "P" / "My Mod" / C.HISTORY_DIR
    history.mkdir(parents=True)
    (history / "mymodule_1_1.7z").write_bytes(b"the first one")
    folder = _downloads(tmp_path, "My Mod", "mymodule_1_1.7z")
    ctrl.remove_old_downloads([folder / "mymodule_1_1.7z"], to_history=True)
    assert (history / "mymodule_1_1.7z").read_bytes() == b"the first one"
    assert len(list(history.iterdir())) == 2


def test_deleting_removes_the_file(tmp_path):
    ctrl = _controller(tmp_path)
    ctrl.create_mod("My Mod")
    folder = _downloads(tmp_path, "My Mod", "old.7z")
    result = ctrl.remove_old_downloads([folder / "old.7z"], to_trash=False)
    assert result["ok"] and result["removed"] == 1
    assert not (folder / "old.7z").exists()


def test_removing_nothing_says_so(tmp_path):
    ctrl = _controller(tmp_path)
    assert ctrl.remove_old_downloads([])["message"] == "Nothing to do."


def test_the_dialog_ticks_only_the_confident_matches(qtbot, tmp_path):
    from vaultkeeper.ui.dialogs.old_downloads import OldDownloadsDialog

    folder = _downloads(tmp_path, "My Mod", "mymodule_1_1.7z", "unrelated.zip")
    old = superseded(sorted(folder.iterdir()), ["mymodule_1_2.7z"])
    dlg = OldDownloadsDialog("My Mod", old)
    qtbot.addWidget(dlg)
    assert [o.name for o in old] == ["mymodule_1_1.7z", "unrelated.zip"]
    assert [p.name for p in dlg.checked_paths()] == ["mymodule_1_1.7z"]


def test_the_dialog_with_nothing_ticked_does_nothing(qtbot, tmp_path):
    from PySide6.QtCore import Qt

    from vaultkeeper.ui.dialogs.old_downloads import OldDownloadsDialog

    folder = _downloads(tmp_path, "My Mod", "mymodule_1_1.7z")
    old = superseded(sorted(folder.iterdir()), ["mymodule_1_2.7z"])
    dlg = OldDownloadsDialog("My Mod", old)
    qtbot.addWidget(dlg)
    dlg.files.topLevelItem(0).setCheckState(0, Qt.CheckState.Unchecked)
    dlg._finish("delete")
    assert dlg.action == ""  # rejected, nothing chosen
