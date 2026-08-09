"""Tests for the Recent Mods menu (VB MsRecentMods / MsNumberRecentMods)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.config.settings import Settings
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow


def _make_mod(profile_mods: Path, name: str, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        path = profile_mods / name / ".Mod Installer" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    _make_mod(profile_mods, "Alpha", {"hak/a.hak": b"AAA"})
    _make_mod(profile_mods, "Beta", {"override/b.2da": b"BBB"})
    _make_mod(profile_mods, "Gamma", {"hak/g.hak": b"GGG"})
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _recent_entries(win: MainWindow) -> list[str]:
    menu = win.nit_menu.action("MsRecentMods").menu()
    return [a.text() for a in menu.actions()]


def test_selecting_a_mod_records_it(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    assert win._recent_mods == []
    assert not win.nit_menu.action("MsRecentMods").isEnabled()

    win._select_mod_by_name("Alpha")
    assert win._recent_mods == ["Alpha"]
    assert win.nit_menu.action("MsRecentMods").isEnabled()
    assert _recent_entries(win) == ["Alpha"]


def test_recent_order_dedup_most_recent_first(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._select_mod_by_name("Beta")
    assert win._recent_mods == ["Beta", "Alpha"]
    # Re-selecting Alpha moves it back to the front (no duplicate).
    win._select_mod_by_name("Alpha")
    assert win._recent_mods == ["Alpha", "Beta"]
    assert _recent_entries(win) == ["Alpha", "Beta"]


def test_numbering_toggle_prefixes_entries(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._select_mod_by_name("Beta")
    # Toggle on numbering (VB MsNumberRecentMods).
    win._on_toggle("MsNumberRecentMods", True)
    assert _recent_entries(win) == ["1. Beta", "2. Alpha"]
    win._on_toggle("MsNumberRecentMods", False)
    assert _recent_entries(win) == ["Beta", "Alpha"]


def test_recent_list_capped_at_max(qtbot, controller, monkeypatch) -> None:
    monkeypatch.setattr(
        "vaultkeeper.config.settings.load_settings",
        lambda *a, **k: Settings(max_recent_mods=2),
    )
    win = MainWindow(controller)
    qtbot.addWidget(win)
    for name in ("Alpha", "Beta", "Gamma"):
        win._select_mod_by_name(name)
    assert win._recent_mods == ["Gamma", "Beta"]  # Alpha dropped (cap 2)


def test_clicking_recent_entry_selects_mod(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._select_mod_by_name("Beta")
    # Trigger the "Alpha" recent entry -> it becomes the selection.
    menu = win.nit_menu.action("MsRecentMods").menu()
    alpha_action = next(a for a in menu.actions() if a.text() == "Alpha")
    alpha_action.trigger()
    assert win.selected_mod_names() == ["Alpha"]


# -- Pin / Unpin / Remove (VB's Actions menu, newtopic47) ----------------------- #
def _entries_with_pins(win) -> list[str]:
    menu = win.nit_menu.action("MsRecentMods").menu()
    return [a.text() for a in menu.actions()]


def test_pinning_keeps_a_mod_at_the_top(qtbot, controller) -> None:
    """A pinned mod is one you keep coming back to; burying it under this
    morning's browsing is the thing pinning exists to stop."""
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._select_mod_by_name("Beta")
    assert win._recent_mods[0] == "Beta"

    win._on_recent_mod_action("pin", "Alpha")

    assert _entries_with_pins(win)[0].endswith("Alpha")
    assert "📌" in _entries_with_pins(win)[0]


def test_a_pinned_mod_survives_the_trim(qtbot, controller) -> None:
    """Trimming drops the oldest — except the one the user asked not to lose."""
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.max_recent_mods = 2
    save_settings(settings)

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._on_recent_mod_action("pin", "Alpha")
    win._select_mod_by_name("Beta")
    win._select_mod_by_name("Gamma")
    win._select_mod_by_name("Beta")

    assert "Alpha" in win._recent_mods, "pinned, so kept past the cap"
    assert len(win._recent_mods) == 3


def test_unpinning_lets_it_fall_back_into_order(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._select_mod_by_name("Beta")
    win._on_recent_mod_action("pin", "Alpha")
    assert _entries_with_pins(win)[0].endswith("Alpha")

    win._on_recent_mod_action("unpin", "Alpha")
    assert _entries_with_pins(win)[0] == "Beta"
    assert "📌" not in " ".join(_entries_with_pins(win))


def test_removing_takes_it_out_of_the_list(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._select_mod_by_name("Beta")

    win._on_recent_mod_action("remove", "Alpha")
    assert win._recent_mods == ["Beta"]
    assert _entries_with_pins(win) == ["Beta"]


def test_pins_persist(qtbot, controller) -> None:
    from vaultkeeper.config.settings import load_settings

    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")
    win._on_recent_mod_action("pin", "Alpha")

    assert load_settings().pinned_recent_mods == ["Alpha"]


def test_each_entry_carries_its_actions_menu(qtbot, controller) -> None:
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._select_mod_by_name("Alpha")

    entry = win.nit_menu.action("MsRecentMods").menu().actions()[0]
    labels = [a.text() for a in entry.menu().actions()]
    assert labels == ["Pin", "Remove from this list"]

    win._on_recent_mod_action("pin", "Alpha")
    entry = win.nit_menu.action("MsRecentMods").menu().actions()[0]
    assert [a.text() for a in entry.menu().actions()] == [
        "Unpin",
        "Remove from this list",
    ]
