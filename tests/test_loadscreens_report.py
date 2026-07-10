"""Controller test for the Start Screen (loadscreen) report (VB StartScreenManager)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from vaultkeeper.core.state import State  # noqa: E402
from vaultkeeper.game import start_screen as ss  # noqa: E402
from vaultkeeper.ui.controller import ProfileController  # noqa: E402


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _setup_loadscreen_mod(controller: ProfileController, names: list[str]) -> Path:
    """Create the managed loadscreen mod with the given image files."""
    controller.create_mod(ss.LOADSCREEN_MOD)
    image_folder = controller.ctx.profile_mods_dir / ss.LOADSCREEN_MOD / ss.SCREEN_FOLDER
    image_folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (image_folder / name).write_bytes(b"x" * 16)
    return image_folder


def test_report_no_mod(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    report = controller.loadscreens_report()
    assert report["exists"] is False
    assert report["images"] == []
    assert "does not yet manage" in report["summary"].lower()


def test_report_lists_images_sorted(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _setup_loadscreen_mod(controller, ["b.tga", "a.tga", "readme.txt"])
    report = controller.loadscreens_report()
    assert report["exists"] is True
    names = [row["name"] for row in report["images"]]
    assert names == ["a.tga", "b.tga"]  # .txt filtered, win-sorted
    assert report["count"] == 2
    assert report["installed"] is False


def test_report_marks_active_from_info_file(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _setup_loadscreen_mod(controller, ["sunset.tga", "castle.tga"])
    # Standard-active info file selecting sunset.tga.
    data_dir = controller._profile_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / ss.INFO_FILENAME).write_text(
        "1\nsunset.tga\n\n/browse\n", encoding="utf-8"
    )
    report = controller.loadscreens_report()
    assert report["active"] == "sunset.tga"
    active_rows = [r for r in report["images"] if r["active"]]
    assert [r["name"] for r in active_rows] == ["sunset.tga"]
    # Not installed → summary says "selected", not "installed".
    assert "selected" in report["summary"].lower()


def test_report_installed_and_excluded(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _setup_loadscreen_mod(controller, ["sunset.tga", "castle.tga", "bad.tga"])
    controller.pd.mod_item(ss.LOADSCREEN_MOD).mod_state = State.INSTALLED
    data_dir = controller._profile_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / ss.INFO_FILENAME).write_text(
        "1\nsunset.tga\n\n/browse\n", encoding="utf-8"
    )
    (data_dir / ss.AUTO_EXCLUDES_FILENAME).write_text("bad.tga\n", encoding="utf-8")

    report = controller.loadscreens_report()
    assert report["installed"] is True
    assert report["excluded_count"] == 1
    excluded = [r["name"] for r in report["images"] if r["excluded"]]
    assert excluded == ["bad.tga"]
    assert "installed" in report["summary"].lower()
    assert "auto-excluded" in report["summary"].lower()


def test_exclusion_add_remove_clear_round_trip(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _setup_loadscreen_mod(controller, ["a.tga", "b.tga", "c.tga"])

    controller.add_loadscreen_exclusion("b.tga")
    controller.add_loadscreen_exclusion("a.tga")
    report = controller.loadscreens_report()
    excluded = {r["name"] for r in report["images"] if r["excluded"]}
    assert excluded == {"a.tga", "b.tga"}
    assert report["excluded_count"] == 2

    controller.remove_loadscreen_exclusion("A.TGA")  # case-insensitive
    report = controller.loadscreens_report()
    excluded = {r["name"] for r in report["images"] if r["excluded"]}
    assert excluded == {"b.tga"}

    controller.clear_loadscreen_exclusions()
    report = controller.loadscreens_report()
    assert report["excluded_count"] == 0


def test_report_surfaces_prefixes(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _setup_loadscreen_mod(controller, ["Winter a.tga", "Summer b.tga", "plain.tga"])
    data_dir = controller._profile_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / ss.PREFIX_FILENAME).write_text("Winter\n!Summer\n", encoding="utf-8")

    report = controller.loadscreens_report()
    assert report["prefix_enabled"] is True
    assert report["prefixed_count"] == 2  # Winter + Summer both defined
    by_name = {r["name"]: r for r in report["images"]}
    assert by_name["Winter a.tga"]["prefixed"] is True
    assert by_name["Winter a.tga"]["filter_prefixed"] is True
    assert by_name["Summer b.tga"]["filter_prefixed"] is False
    assert by_name["plain.tga"]["prefixed"] is False
    assert "2 prefixed" in report["summary"]


def test_report_no_prefixes_omits_from_summary(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _setup_loadscreen_mod(controller, ["a.tga"])
    report = controller.loadscreens_report()
    assert report["prefix_enabled"] is False
    assert "prefixed" not in report["summary"]


def test_add_exclusion_dedups_on_persist(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    _setup_loadscreen_mod(controller, ["a.tga"])
    controller.add_loadscreen_exclusion("a.tga")
    controller.add_loadscreen_exclusion("a.tga")  # duplicate
    report = controller.loadscreens_report()
    assert report["excluded_count"] == 1
