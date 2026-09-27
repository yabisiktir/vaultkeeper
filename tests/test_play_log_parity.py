"""Play data and logs as NIT handles them (logic audit 3e).

* NIT reports the hak files the game could not load after a session ("Module
  Load Failure", with Copy to Clipboard); VK parsed them and said nothing.
* NIT matches the log's markers without regard to case.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from vaultkeeper.game.client_log import parse_client_log
from vaultkeeper.ui.controller import ProfileController


def test_log_markers_ignore_case() -> None:
    lines = [
        "[Thu Nov 02 17:00:00] LOADING MODULE: mymod",
        "[Thu Nov 02 17:30:00] server shutting down",
    ]
    result = parse_client_log(
        lines,
        datetime(2026, 11, 2, 16, 59),
        datetime(2026, 11, 2, 17, 31),
        is_engine_log=False,
        mods_started={},
    )
    assert result.mods_loaded["mymod"].total_seconds() == 30 * 60


def test_missing_haks_are_reported_after_play(qtbot, tmp_path: Path, monkeypatch) -> None:
    from vaultkeeper.ui.main_window import MainWindow

    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    win = MainWindow(c)
    qtbot.addWidget(win)
    monkeypatch.setattr(
        c, "process_play_session", lambda *_: {"mods": {}, "missing_hak_files": ["cep2_top.hak"]}
    )
    shown = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: shown.append(self.text()) or 0)
    win._play_started = datetime.now()

    win._on_game_exited()

    assert shown and "cep2_top.hak" in shown[0]
