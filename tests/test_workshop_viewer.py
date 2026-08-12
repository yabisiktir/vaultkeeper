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


# -- Refresh diff + rename (VB ValidateSteamContent / RenameMod) ----------- #


def test_workshop_refresh_persists_and_diffs(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_item(content, "111", "override/a.tga")
    _make_item(content, "222", "override/b.tga")
    controller = _controller(tmp_path, content, game_root)

    # First refresh: both subscriptions are new; the DB is persisted.
    first = controller.workshop_refresh()
    assert sorted(first["added"]) == ["111", "222"]
    assert controller._workshop_contents_file().is_file()

    # No changes on a second refresh.
    second = controller.workshop_refresh()
    assert not second["added"] and not second["updated"] and not second["unsubscribed"]

    # Unsubscribe 222; refresh detects it.
    import shutil

    shutil.rmtree(content / "222")
    third = controller.workshop_refresh()
    assert third["unsubscribed"] == ["222"]


def test_workshop_rename(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_item(content, "111", "override/a.tga")
    controller = _controller(tmp_path, content, game_root)
    controller.workshop_refresh()

    result = controller.rename_workshop_mod("111", "My Renamed Mod")
    assert result["ok"]
    stored = controller._read_workshop_contents()
    assert stored["111"].mod_name == "My Renamed Mod"


def test_dialog_refresh_runs_diff(qtbot, tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_item(content, "111", "override/a.tga")
    controller = _controller(tmp_path, content, game_root)
    dlg = WorkshopViewer.show_for(controller)
    qtbot.addWidget(dlg)
    dlg._on_refresh()
    assert "Workshop Subscriptions: 1" in dlg.summary.text()
    assert controller._workshop_contents_file().is_file()


# -- Add as managed mod (VB SteamWorkshop.CreateModFolder) ----------------- #


def _make_named_item(content: Path, item_id: str, mod_stem: str) -> None:
    """A subscription whose ``modules/<stem>.mod`` names it (VB GetModFolderName)."""
    _make_item(content, item_id, f"modules/{mod_stem}.mod", "override/tex.tga")


def test_workshop_url_format():
    from vaultkeeper.game.workshop import workshop_url

    assert (
        workshop_url("12345")
        == "https://steamcommunity.com/sharedfiles/filedetails/?id=12345"
    )


def test_add_workshop_mod_creates_managed_mod(tmp_path):
    from vaultkeeper.core.archive import FakeArchiveExtractor
    from vaultkeeper.game.workshop import WORKSHOP_GROUP, workshop_url

    game_root, content = _steam_layout(tmp_path)
    _make_named_item(content, "999", "Cool Adventure")
    controller = _controller(tmp_path, content, game_root)
    controller._extractor = FakeArchiveExtractor()

    result = controller.add_workshop_mod("999", build_installer=False)
    assert result["ok"] and result["created"] and result["archived"]
    assert result["mod_name"] == "Cool Adventure"

    md = controller.pd.mod_item("Cool Adventure")
    assert md is not None
    assert md.group == WORKSHOP_GROUP
    assert md.workshop_id == "999"
    assert md.web_link == workshop_url("999")

    # The subscription content was archived into the mod's _Workshop folder.
    archive = (
        tmp_path / "Profiles" / "P" / "Cool Adventure" / C.WORKSHOP_DIR
        / "Cool Adventure (999).7z"
    )
    assert archive.is_file()
    assert len(controller._extractor.create_calls) == 1


def test_add_workshop_mod_already_managed_is_noop(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_named_item(content, "111", "Alpha Mod")  # id 111 already claimed by Alpha Mod
    controller = _controller(tmp_path, content, game_root)

    result = controller.add_workshop_mod("111", build_installer=False)
    assert result["ok"] and not result["created"]
    assert "already managed" in result["message"]


def test_add_workshop_mod_name_clash_refused(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_named_item(content, "999", "Beta Mod")  # Beta Mod exists, not a workshop mod
    controller = _controller(tmp_path, content, game_root)

    result = controller.add_workshop_mod("999", build_installer=False)
    assert not result["ok"]
    assert "already exists" in result["message"]


def test_add_workshop_mod_non_steam_and_unsubscribed(tmp_path):
    # Non-Steam install.
    game_root = tmp_path / "GOG" / "Neverwinter Nights"
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    game_root.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods, game_root=game_root
    )
    assert "not a Steam install" in controller.add_workshop_mod("1")["message"]

    # Steam install but the id isn't subscribed.
    game_root2, content = _steam_layout(tmp_path / "steam")
    controller2 = _controller(tmp_path / "steam", content, game_root2)
    assert "not subscribed" in controller2.add_workshop_mod("nope")["message"]


def test_dialog_add_button_enabled_only_for_unmanaged(qtbot, tmp_path):
    game_root, content = _steam_layout(tmp_path)
    _make_item(content, "111", "readme.txt")  # managed by Alpha Mod
    _make_named_item(content, "999", "Cool Adventure")  # unmanaged
    controller = _controller(tmp_path, content, game_root)
    dlg = WorkshopViewer.show_for(controller)
    qtbot.addWidget(dlg)

    by_id = {
        dlg.items.topLevelItem(i).text(0): i
        for i in range(dlg.items.topLevelItemCount())
    }
    dlg.items.setCurrentItem(dlg.items.topLevelItem(by_id["111"]))
    assert not dlg.add_button.isEnabled()  # managed -> can't add
    dlg.items.setCurrentItem(dlg.items.topLevelItem(by_id["999"]))
    assert dlg.add_button.isEnabled()  # unmanaged -> can add


def test_dialog_add_invokes_controller(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from vaultkeeper.core.archive import FakeArchiveExtractor

    game_root, content = _steam_layout(tmp_path)
    _make_named_item(content, "999", "Cool Adventure")
    controller = _controller(tmp_path, content, game_root)
    controller._extractor = FakeArchiveExtractor()

    dlg = WorkshopViewer.show_for(controller)
    qtbot.addWidget(dlg)
    dlg.items.setCurrentItem(dlg.items.topLevelItem(0))
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dlg._on_add()
    assert controller.pd.mod_item("Cool Adventure") is not None


# -- Enable + folder override (newtopic19.htm) ---------------------------- #


def test_management_is_off_by_default(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    controller = _controller(tmp_path, content, game_root)
    # "By default, the Installer Tool does not manage Steam's Workshop content."
    assert controller.workshop_management_enabled() is False


def test_management_reflects_the_preference(tmp_path):
    from vaultkeeper.config.settings import load_settings, save_settings

    game_root, content = _steam_layout(tmp_path)
    controller = _controller(tmp_path, content, game_root)
    settings = load_settings()
    settings.manage_steam_workshop = True
    save_settings(settings)
    assert controller.workshop_management_enabled() is True


def test_content_dir_falls_back_to_the_steam_layout(tmp_path):
    game_root, content = _steam_layout(tmp_path)
    controller = _controller(tmp_path, content, game_root)
    # No override set: the auto-detected Steam path is used.
    assert controller.workshop_content_dir() == content


def test_a_manual_override_wins_over_detection(tmp_path):
    from vaultkeeper.config.settings import load_settings, save_settings

    game_root, content = _steam_layout(tmp_path)
    controller = _controller(tmp_path, content, game_root)

    elsewhere = tmp_path / "custom" / "workshop"
    elsewhere.mkdir(parents=True)
    settings = load_settings()
    settings.workshop_content_dir = str(elsewhere)
    save_settings(settings)

    assert controller.workshop_content_dir() == elsewhere


def test_a_manual_override_that_is_not_there_is_ignored(tmp_path):
    from vaultkeeper.config.settings import load_settings, save_settings

    game_root, content = _steam_layout(tmp_path)
    controller = _controller(tmp_path, content, game_root)
    settings = load_settings()
    settings.workshop_content_dir = str(tmp_path / "gone")
    save_settings(settings)
    # A path to nothing is not usable, and is not silently treated as one.
    assert controller.workshop_content_dir() is None


def test_override_lets_detection_work_on_a_non_steam_install(tmp_path):
    """The whole point: a GOG install could not see the Workshop at all before."""
    from vaultkeeper.config.settings import load_settings, save_settings

    game_root = tmp_path / "GOG" / "Neverwinter Nights"
    game_root.mkdir(parents=True)
    content = tmp_path / "manual-workshop"
    content.mkdir()
    _make_item(content, "111", "readme.txt")

    controller = _controller(tmp_path, content, game_root)
    settings = load_settings()
    settings.workshop_content_dir = str(content)
    save_settings(settings)

    report = controller.workshop_report()
    assert report["content_path"] == str(content)
    assert {r["id"] for r in report["rows"]} == {"111"}
