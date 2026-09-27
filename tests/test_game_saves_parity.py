"""Game saves as NIT handles them (logic audit 3d).

* Reduce keeps ``ConfigSavesRetention`` saves (50), remembered between uses;
  Vaultkeeper started at 100 every time.
* After a game session NIT warns when there are more saves than
  ``ConfigSavesThreshold`` (700); Vaultkeeper said nothing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vaultkeeper.config.settings import Settings, load_settings
from vaultkeeper.ui.controller import ProfileController


def _controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    user = tmp_path / "user"
    (user / "saves").mkdir(parents=True)
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
        game_user_dir=user,
    )


def test_defaults() -> None:
    assert Settings().saves_retention == 50
    assert Settings().saves_threshold == 700


def test_reduce_keep_count_is_remembered(qtbot, tmp_path: Path) -> None:
    from vaultkeeper.ui.dialogs.game_saves_manager import GameSavesManager

    c = _controller(tmp_path)
    dlg = GameSavesManager(c.game_saves_report(), c)
    qtbot.addWidget(dlg)
    assert dlg.keep_spin.value() == 50
    dlg.keep_spin.setValue(90)
    assert load_settings().saves_retention == 90


def test_too_many_saves_are_reported_after_play(qtbot, tmp_path: Path, monkeypatch) -> None:
    from vaultkeeper.config.settings import save_settings
    from vaultkeeper.ui.main_window import MainWindow

    c = _controller(tmp_path)
    for i in range(4):
        (tmp_path / "user" / "saves" / f"{i:06d} - save").mkdir()
    settings = load_settings()
    settings.saves_threshold = 3
    save_settings(settings)
    win = MainWindow(c)
    qtbot.addWidget(win)
    monkeypatch.setattr(c, "process_play_session", lambda *_: {"mods": {}})
    win._play_started = datetime.now()

    win._on_game_exited()

    assert "There are 4 game saves" in win.nit_status.mg_info.text()
