"""Tests for the Steam Workshop viewer (domain scan + controller report + dialog).

Covers the bounded VB ``WorkshopViewer`` slice: enumerate subscription id folders
under Steam's Workshop content path, mark each managed when a mod claims its id,
and show the selected item's folder contents.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from vaultkeeper.core import constants as C  # noqa: E402
from vaultkeeper.game.workshop import (  # noqa: E402
    scan_workshop,
    workshop_content_path,
)
from vaultkeeper.ui.controller import ProfileController  # noqa: E402
from vaultkeeper.ui.dialogs.workshop_viewer import WorkshopViewer  # noqa: E402


def _steam_layout(tmp_path: Path) -> tuple[Path, Path]:
    """A Steam-shaped install: return (game_root, workshop content path)."""
    steamapps = tmp_path / "steamapps"
    game_root = steamapps / "common" / "Neverwinter Nights"
    content = steamapps / "workshop" / "content" / "704450"
    content.mkdir(parents=True)
    game_root.mkdir(parents=True)
    return game_root, content


def _make_item(content: Path, item_id: str, *files: str) -> None:
    folder = content / item_id
    folder.mkdir()
    for name in files:
        f = folder / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"data")


# -- Domain slice --------------------------------------------------------- #


def test_content_path_derived_for_steam_install(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    assert workshop_content_path(game_root) == content


def test_content_path_none_for_non_steam_install(tmp_path):
    game_root = tmp_path / "GOG" / "Neverwinter Nights"
    game_root.mkdir(parents=True)
    assert workshop_content_path(game_root) is None


def test_scan_maps_managed_and_sorts_by_mod(tmp_path):
    _, content = _steam_layout(tmp_path)
    _make_item(content, "111", "a.hak")
    _make_item(content, "222", "b.hak")
    _make_item(content, "333")  # unmanaged
    (content / "not_an_id").mkdir()  # ignored (non-numeric)

    items = scan_workshop(content, {"222": "Zeta Mod", "111": "Alpha Mod"})
    assert [(it.id, it.managed, it.mod_name) for it in items] == [
        ("333", False, ""),  # unmanaged (empty name) sorts first
        ("111", True, "Alpha Mod"),
        ("222", True, "Zeta Mod"),
    ]


# -- Controller report ---------------------------------------------------- #


def _controller(tmp_path: Path, content: Path, game_root: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    for name in ("Alpha Mod", "Beta Mod"):
        f = profile_mods / name / C.MOD_INSTALLER_DIR / "hak" / "x.hak"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=game_root,
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.pd.mod_item("Alpha Mod").workshop_id = "111"
    return controller


def test_report_uses_mod_workshop_ids(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_item(content, "111", "readme.txt")
    _make_item(content, "999")
    controller = _controller(tmp_path, content, game_root)

    report = controller.workshop_report()
    by_id = {r["id"]: r for r in report["rows"]}
    assert by_id["111"]["managed"] == "Yes"
    assert by_id["111"]["mod"] == "Alpha Mod"
    assert by_id["999"]["managed"] == "No"
    assert report["managed"] == 1
    assert report["unmanaged"] == 1
    assert report["summary"] == "Workshop Subscriptions: 2. Managed: 1. Unmanaged: 1."
    assert report["content_path"] == str(content)


def test_report_empty_for_non_steam_install(tmp_path):
    game_root = tmp_path / "GOG" / "Neverwinter Nights"
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    game_root.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods, game_root=game_root
    )
    report = controller.workshop_report()
    assert report["rows"] == []
    assert report["summary"] == "Steam Workshop Subscriptions detected: None."


def test_item_files_lists_folder_contents(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_item(content, "111", "readme.txt", "hak/big.hak")
    controller = _controller(tmp_path, content, game_root)
    files = controller.workshop_item_files(str(content / "111"))
    assert {f["name"] for f in files} == {"readme.txt", str(Path("hak") / "big.hak")}


# -- Dialog --------------------------------------------------------------- #


def test_dialog_populates_and_shows_contents(qtbot, tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_item(content, "111", "readme.txt")
    controller = _controller(tmp_path, content, game_root)

    dlg = WorkshopViewer.show_for(controller)
    qtbot.addWidget(dlg)
    assert dlg.items.topLevelItemCount() == 1
    first = dlg.items.topLevelItem(0)
    assert first.text(0) == "111"
    assert first.text(2) == "Alpha Mod"
    # First item selected on open -> its contents shown.
    assert dlg.contents.topLevelItemCount() == 1
    assert dlg.contents.topLevelItem(0).text(0) == "readme.txt"
