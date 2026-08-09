"""Mod and File Status Icons (statusicons.htm).

"Descriptions of the status icons are displayed in the Mod Properties and
Details Property panels." The port showed the enum name title-cased, so a mod
sat there saying "Some And Overridden" — a label, not an explanation.

Found by *reading* the topic. All three machine sweeps called it quiet: it names
no command, describes no click, and makes no "the Tool will…" promise. Its
content is a table of icons and meanings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.core.state import State
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def test_every_state_a_mod_can_be_in_has_a_description():
    """A state with no description falls back to its enum name, which is the
    thing this exists to stop — so the fallback must never be reached."""
    real = [s for s in State if s not in (State.INSTALL_STATE,)]
    for state in real:
        described = state.describe()
        assert described.endswith("."), state.name
        assert described != state.name.replace("_", " ").title(), state.name


def test_files_and_mods_are_worded_differently_where_it_matters():
    """A file is overridden by *a* file; a mod by the files of other mods."""
    assert "another mod's file" in State.OVERRIDDEN.describe(of_file=True)
    assert "other mods" in State.OVERRIDDEN.describe()


def test_the_descriptions_say_what_the_help_says():
    assert State.NONE.describe() == "This mod does not have a Mod Installer."
    assert "identical" in State.MATCH_OVERRIDE.describe()
    assert "Some, but not all" in State.INSTALLED_AND_OVERRIDDEN.describe()


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    payload = tmp_path / "Profiles" / "P" / "Alpha" / ".Mod Installer" / "hak"
    payload.mkdir(parents=True)
    (payload / "a.hak").write_bytes(b"x")
    return ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def test_the_mod_list_row_explains_its_own_icon(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert win._tree.select_mod("Alpha")
    item = win._tree.currentItem()

    md = controller.pd.mod_item("Alpha")
    assert item.toolTip(0) == md.mod_state.describe()
    assert item.toolTip(0) != "", "an icon with no explanation is a puzzle"


def test_the_details_panel_explains_the_state(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")

    rows = {
        win._details_list.topLevelItem(i).text(0): win._details_list.topLevelItem(i)
        for i in range(win._details_list.topLevelItemCount())
    }
    assert "State" in rows
    assert rows["State"].toolTip(1) == controller.pd.mod_item("Alpha").mod_state.describe()


def test_a_contents_row_explains_its_file_icon(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")

    folder = win._contents.topLevelItem(0)
    assert folder is not None
    file_row = folder.child(0)
    assert file_row.toolTip(0).startswith("This file")
