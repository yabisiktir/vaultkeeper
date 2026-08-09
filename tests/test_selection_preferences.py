"""Selection Preferences and Selection History (newtopic34 / newtopic63).

Three findings from reading one topic, all the same feature:

* the Selection Preferences icon had no click handler — the status bar emitted
  ``select_file_clicked`` into the void;
* so did the mod count;
* and *Clear Selection History* cleared the Recent Mods list, which is a
  different list reached by a different command.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.config.settings import load_settings, save_settings
from vaultkeeper.core import constants as C
from vaultkeeper.ui import selection_prefs as sp
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


# -- Choosing --------------------------------------------------------------------- #
FILES = [("hak", "a.hak"), ("docs", "readme.txt"), ("docs", "guide.rtf"),
         ("nitconfig", C.PLAY_TIME_FILE)]


def test_the_first_document_wins_by_extension_order():
    """rtf before txt, as VB prefers."""
    assert sp.choose(sp.TEXT_FILE, FILES) == ("docs", "guide.rtf")


def test_the_play_time_record_can_be_asked_for():
    assert sp.choose(sp.PLAY_TIME, FILES) == ("nitconfig", C.PLAY_TIME_FILE)


def test_history_uses_what_was_remembered():
    assert sp.choose(sp.HISTORY, FILES, remembered=("hak", "a.hak")) == ("hak", "a.hak")


def test_a_remembered_file_that_has_gone_falls_through():
    """A mod's files change; the memory of one that is no longer there must not
    leave the pane on nothing."""
    chosen = sp.choose(sp.HISTORY, FILES, remembered=("hak", "deleted.hak"))
    assert chosen == ("docs", "guide.rtf")


def test_no_document_means_no_selection_rather_than_any_file():
    """Selecting a .hak because there is no readme puts the pane on something
    nobody asked to look at."""
    assert sp.choose(sp.TEXT_FILE, [("hak", "a.hak")]) is None


def test_an_empty_mod_chooses_nothing():
    assert sp.choose(sp.TEXT_FILE, []) is None


# -- In the window ----------------------------------------------------------------- #
@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    payload = tmp_path / "Profiles" / "P" / "Alpha" / C.MOD_INSTALLER_DIR
    (payload / "hak").mkdir(parents=True)
    (payload / "docs").mkdir(parents=True)
    (payload / "hak" / "a.hak").write_bytes(b"x")
    (payload / "docs" / "readme.txt").write_bytes(b"x")
    settings = load_settings()
    settings.selection_preference = "text_file"
    settings.contents_selection = {}
    save_settings(settings)
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_selecting_a_mod_opens_its_contents_on_the_document(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")

    assert win._contents.selected_file() == ("docs", "readme.txt")


def test_the_preference_is_honoured(qtbot, controller):
    settings = load_settings()
    settings.selection_preference = "history"
    settings.contents_selection = {"Alpha": "hak/a.hak"}
    save_settings(settings)

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")

    assert win._contents.selected_file() == ("hak", "a.hak")


def test_the_selection_is_remembered(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._contents.select_file(("hak", "a.hak"))

    win._remember_contents_selection()
    assert load_settings().contents_selection["Alpha"] == "hak/a.hak"


def test_both_status_bar_signals_now_reach_something(qtbot, controller):
    from PySide6.QtCore import QMetaMethod

    win = MainWindow(controller)
    qtbot.addWidget(win)
    bar = win.nit_status
    meta = bar.metaObject()

    for name in ("mod_count_clicked", "select_file_clicked"):
        method = next(
            meta.method(i)
            for i in range(meta.methodCount())
            if meta.method(i).methodType() == QMetaMethod.MethodType.Signal
            and bytes(meta.method(i).name()).decode() == name
        )
        assert bar.isSignalConnected(method), f"{name} still emits into the void"


def test_picking_a_file_records_it_without_being_asked(qtbot, controller):
    """The remembering has to happen on selection, or "last time" never has an
    answer — the method existed and nothing called it, which is the same defect
    as the two dead signals above."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")

    win._contents.select_file(("hak", "a.hak"))
    assert load_settings().contents_selection.get("Alpha") == "hak/a.hak"


def test_reopening_the_mod_returns_to_it(qtbot, controller):
    settings = load_settings()
    settings.selection_preference = "history"
    save_settings(settings)

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._contents.select_file(("hak", "a.hak"))

    from vaultkeeper.core.mod_data import ModData

    controller.pd.add_mod(ModData(group="G", mod_name="Other"))
    win.refresh()
    win._select_mod_by_name("Alpha")

    assert win._contents.selected_file() == ("hak", "a.hak")
