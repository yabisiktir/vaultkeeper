"""Each profile remembers its selected mods (VB ProfileData.LoadSelections / SaveSelections)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def _controller(tmp_path: Path, name: str = "P") -> ProfileController:
    mods = tmp_path / "Profiles" / name
    mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / f"{name}.json",
    )
    for mod in ("Alpha", "Beta", "Gamma"):
        c.create_mod(mod)
    return c


def test_selections_round_trip_and_tolerate_a_bad_file(tmp_path) -> None:
    c = _controller(tmp_path)
    assert c.load_selections() == []
    c.save_selections(["Beta", "Gamma"])
    assert c.load_selections() == ["Beta", "Gamma"]
    (c._profile_data_dir() / c.SELECTIONS_FILE).write_text("not json")
    assert c.load_selections() == []


def test_a_nit_selections_file_is_never_read(tmp_path) -> None:
    c = _controller(tmp_path)
    (c._profile_data_dir()).mkdir(parents=True, exist_ok=True)
    (c._profile_data_dir() / "ProfileSelections.txt").write_text("FvMods|1|2")
    assert c.load_selections() == []


def test_the_window_reselects_what_was_selected_when_it_closed(qtbot, tmp_path) -> None:
    c = _controller(tmp_path)
    win = MainWindow(c)
    qtbot.addWidget(win)
    win._tree.select_mods(["Beta"])
    win.close()
    assert c.load_selections() == ["Beta"]

    again = MainWindow(c)
    qtbot.addWidget(again)
    assert again._tree.selected_mod_names() == ["Beta"]
    assert again._tree.currentItem().text(0) == "Beta"


def test_switching_profile_saves_the_outgoing_selection(qtbot, tmp_path) -> None:
    first, second = _controller(tmp_path, "P"), _controller(tmp_path, "Q")
    second.save_selections(["Gamma"])
    win = MainWindow(first)
    qtbot.addWidget(win)
    win._tree.select_mods(["Alpha"])

    win.set_controller(second)

    assert first.load_selections() == ["Alpha"]
    assert win._tree.selected_mod_names() == ["Gamma"]
