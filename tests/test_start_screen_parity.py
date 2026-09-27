"""Start screens, as NIT does them (logic audit stage 3g).

With "Auto-Start Screen Selection" on, NIT installs the next start screen each
time the game closes (``BgRunNwn`` → ``AutoLoadscreen``); Shift+right-click on
Play switches between the Standard and Prefixed sets. Vaultkeeper stored the
setting and never acted on it.
"""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game import start_screen as ss
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path, names=("A.tga", "B.tga", "C.tga")) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    md = c.ensure_loadscreen_mod()
    for name in names:
        (c._loadscreen_image_folder(md) / name).write_bytes(name.encode())
    assert c.install_loadscreen(names[0])["ok"]
    return c


def _installed(c: ProfileController) -> bytes:
    return c.installed_loadscreen_path().read_bytes()


def test_the_next_screen_is_installed_in_turn(tmp_path: Path) -> None:
    c = _controller(tmp_path)

    assert c.next_loadscreen()["installed"] == "B.tga"
    assert _installed(c) == b"B.tga"
    assert c.next_loadscreen()["installed"] == "C.tga"
    assert c.next_loadscreen()["installed"] == "A.tga"  # wraps round


def test_excluded_screens_are_skipped(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.add_loadscreen_exclusion("B.tga")

    assert c.next_loadscreen()["installed"] == "C.tga"


def test_nothing_happens_without_an_installed_screen_mod(tmp_path: Path) -> None:
    c = _controller(tmp_path)
    c.uninstall_loadscreen()

    assert not c.next_loadscreen()["ok"]


def test_prefixed_set_and_toggle(tmp_path: Path) -> None:
    c = _controller(tmp_path, names=("A.tga", "B.tga", "X one.tga", "X two.tga"))
    c.save_loadscreen_prefixes("X\n")

    toggled = c.next_loadscreen(toggle=True)  # Standard → Prefixed; nothing chosen yet
    info = ss.read_start_screen_info(c._profile_data_dir())
    assert info.prefix_active and not toggled["ok"]

    c.install_loadscreen("X one.tga", prefixed=True)
    assert c.next_loadscreen()["installed"] == "X two.tga"
    assert ss.read_start_screen_info(c._profile_data_dir()).prefix_active

    back = c.next_loadscreen(toggle=True)  # Prefixed → Standard: its own last screen
    assert back["installed"] == "A.tga"
    assert ss.read_start_screen_info(c._profile_data_dir()).standard_active


def test_a_standard_screen_named_like_a_prefix_keeps_the_standard_set(tmp_path: Path) -> None:
    """NIT keeps the active type; picking by name flipped the set."""
    c = _controller(tmp_path, names=("A.tga", "X one.tga"))
    c.save_loadscreen_prefixes("X\n")

    assert c.next_loadscreen()["installed"] == "X one.tga"
    assert ss.read_start_screen_info(c._profile_data_dir()).standard_active


def test_game_exit_rotates_when_the_setting_is_on(qtbot, tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime

    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.ui.main_window import MainWindow

    c = _controller(tmp_path)
    win = MainWindow(c)
    qtbot.addWidget(win)
    monkeypatch.setattr(c, "process_play_session", lambda *a: {"mods": {}})
    win._play_started = datetime.now()
    win._on_game_exited()
    assert _installed(c) == b"A.tga"  # off by default, as in NIT

    settings = load_settings()
    settings.auto_loadscreen = True
    save_settings(settings)
    win._play_started = datetime.now()
    win._on_game_exited()
    assert _installed(c) == b"B.tga"


def test_delete_goes_to_the_recycle_bin(tmp_path: Path, recycle_bin: Path) -> None:
    c = _controller(tmp_path)

    c.delete_loadscreen_images(["C.tga"])

    assert [p.read_bytes() for p in recycle_bin.rglob("C.tga")] == [b"C.tga"]


def test_deleting_the_active_screen_refills_from_its_own_set(tmp_path: Path) -> None:
    """NIT keeps the active type and skips excluded images; the old code took the
    first image by name and flipped to Prefixed if it looked prefixed."""
    c = _controller(tmp_path, names=("B.tga", "A.tga", "X one.tga"))
    c.save_loadscreen_prefixes("X\n")
    c.install_loadscreen("B.tga", prefixed=False)
    c.add_loadscreen_exclusion("A.tga")

    c.delete_loadscreen_images(["B.tga"])

    info = ss.read_start_screen_info(c._profile_data_dir())
    assert info.standard_active and info.standard == "X one.tga"
    assert c.installed_loadscreen_path() is None  # uninstalled (auto-select off)


def test_with_auto_select_the_new_active_screen_is_installed(tmp_path: Path) -> None:
    from vaultkeeper.config.settings import load_settings, save_settings

    settings = load_settings()
    settings.auto_loadscreen = True
    save_settings(settings)
    c = _controller(tmp_path)

    c.delete_loadscreen_images(["A.tga"])

    assert _installed(c) == b"B.tga"


def test_rotation_survives_renaming_the_installed_screen(tmp_path: Path) -> None:
    """NIT's rename bug (@1271) left the active name on the old file, so the next
    rotation found nothing. The rename button used the replicated bug."""
    c = _controller(tmp_path)

    assert c.rename_loadscreen_image("A.tga", "Z.tga")["ok"]

    raw = (c._profile_data_dir() / ss.INFO_FILENAME).read_text().splitlines()
    assert raw[0] == "1" and raw[1] == "Z.tga"
    assert c.next_loadscreen()["installed"] == "B.tga"
