"""Tests for the Steam Workshop contents diff (VB SteamWorkshop.ValidateSteamContent)."""

from __future__ import annotations

import time
from pathlib import Path

from tests import real_data

_REAL_WS = real_data.steam_workshop()


def _item(content: Path, id_: str, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        p = content / id_ / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def test_diff_first_run_all_added(tmp_path):
    from vaultkeeper.game.workshop import diff_workshop

    content = tmp_path / "704450"
    _item(content, "111", {"override/a.tga": b"x", "override/b.mdl": b"yy"})
    _item(content, "222", {"override/c.tga": b"z"})

    diff = diff_workshop(content, {})
    assert sorted(diff.added) == ["111", "222"]
    assert diff.added_files == 3
    assert not diff.updated and not diff.unsubscribed
    assert set(diff.contents) == {"111", "222"}
    assert "Added: 2" in diff.summary


def test_diff_detects_update_remove_unsubscribe(tmp_path):
    from vaultkeeper.game.workshop import contents_from_json, contents_to_json, diff_workshop

    content = tmp_path / "704450"
    _item(content, "111", {"override/a.tga": b"x", "override/b.mdl": b"yy"})
    _item(content, "222", {"override/c.tga": b"z"})
    stored = contents_from_json(contents_to_json(diff_workshop(content, {}).contents))

    # Change 111's a.tga (size differs), delete 222's whole folder.
    time.sleep(0.01)
    (content / "111" / "override" / "a.tga").write_bytes(b"xxxxx")
    import shutil

    shutil.rmtree(content / "222")

    diff = diff_workshop(content, stored)
    assert diff.updated == ["111"]  # 111 changed
    assert diff.unsubscribed == ["222"]
    assert diff.updated_files == 1
    assert "222" not in diff.contents


def test_resolve_mod_name_from_module(tmp_path):
    from vaultkeeper.game.workshop import resolve_mod_name

    folder = tmp_path / "333"
    (folder / "modules").mkdir(parents=True)
    (folder / "modules" / "Cool Adventure.mod").write_bytes(b"m")
    assert resolve_mod_name(folder, "333") == "Cool Adventure"
    # No module → "Mod <id>".
    assert resolve_mod_name(tmp_path / "444", "444") == "Mod 444"


import pytest  # noqa: E402


@pytest.mark.skipif(_REAL_WS is None, reason=real_data.REASON)
def test_diff_real_workshop_folder_stable():
    from vaultkeeper.game.workshop import contents_from_json, contents_to_json, diff_workshop

    first = diff_workshop(_REAL_WS, {})
    assert len(first.added) >= 10  # the real folder has ~15 subscriptions
    assert first.added_files > 1000
    # Persisting then re-diffing yields no changes (stable).
    stored = contents_from_json(contents_to_json(first.contents))
    second = diff_workshop(_REAL_WS, stored)
    assert not second.added and not second.updated and not second.unsubscribed


# -- Detection on profile load (newtopic20.htm) ---------------------------------- #
def test_loading_a_profile_looks_for_new_subscriptions(qtbot, tmp_path):
    """"The Installer Tool detects new and changed Workshop Subscriptions when
    you […] Load or reload an Enhanced Edition Profile." Only the Tools menu and
    the viewer did it, so something subscribed to yesterday stayed invisible
    until someone went looking."""
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )

    calls: list[int] = []
    controller.workshop_refresh = lambda: (
        calls.append(1),
        {"added": ["123"], "updated": [], "unsubscribed": [], "summary": "1 new"},
    )[1]

    win = MainWindow(None)
    qtbot.addWidget(win)
    win.set_controller(controller)

    assert calls == [1]
    assert "1 new" in win.nit_status.mg_info.text()


def test_nothing_is_said_when_nothing_changed(qtbot, tmp_path):
    """A profile load is not the moment for a message saying nothing happened."""
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    controller.workshop_refresh = lambda: {
        "added": [], "updated": [], "unsubscribed": [], "summary": "This is not a Steam install."
    }

    win = MainWindow(None)
    qtbot.addWidget(win)
    win.set_controller(controller)
    assert "not a Steam install" not in win.nit_status.mg_info.text()


def test_a_failure_never_stops_a_profile_opening(qtbot, tmp_path):
    from vaultkeeper.ui.controller import ProfileController
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    controller = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )

    def boom():
        raise OSError("steam is not there")

    controller.workshop_refresh = boom

    win = MainWindow(None)
    qtbot.addWidget(win)
    win.set_controller(controller)  # must not raise
    assert win.controller is controller
