"""Tests for the config-isolation guard (detect game-config drift, never write it)."""

from __future__ import annotations

from pathlib import Path

from vaultkeeper.game.config_guard import ChangeKind, ConfigGuard, snapshot


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_first_run_reports_added(tmp_path: Path) -> None:
    game = tmp_path / "Neverwinter Nights"
    _write(game / "nwn.ini", "[Display]\nWidth=1920\n")
    guard = ConfigGuard(game, snapshot_path=tmp_path / "snap.json")
    changes = guard.check()
    assert [c.kind for c in changes] == [ChangeKind.ADDED]
    assert changes[0].path == game / "nwn.ini"


def test_in_sync_after_accept(tmp_path: Path) -> None:
    game = tmp_path / "nwn"
    _write(game / "nwn.ini", "a=1\n")
    guard = ConfigGuard(game, snapshot_path=tmp_path / "snap.json")
    guard.accept()
    assert guard.check() == []


def test_detects_modification(tmp_path: Path) -> None:
    game = tmp_path / "nwn"
    ini = game / "nwn.ini"
    _write(ini, "a=1\n")
    guard = ConfigGuard(game, snapshot_path=tmp_path / "snap.json")
    guard.accept()
    _write(ini, "a=2\n")  # user or game changed it out of band
    changes = guard.check()
    assert [c.kind for c in changes] == [ChangeKind.MODIFIED]


def test_detects_removal(tmp_path: Path) -> None:
    game = tmp_path / "nwn"
    ini = game / "settings.tml"
    _write(ini, "x\n")
    guard = ConfigGuard(game, snapshot_path=tmp_path / "snap.json")
    guard.accept()
    ini.unlink()
    changes = guard.check()
    assert [c.kind for c in changes] == [ChangeKind.REMOVED]


def test_guard_never_writes_game_files(tmp_path: Path) -> None:
    game = tmp_path / "nwn"
    ini = game / "nwn.ini"
    _write(ini, "original\n")
    guard = ConfigGuard(game, snapshot_path=tmp_path / "snap.json")
    guard.check()
    guard.accept()
    guard.check()
    # The game file is untouched; only VK's own snapshot file is written.
    assert ini.read_text() == "original\n"
    assert (tmp_path / "snap.json").exists()


def test_snapshot_only_includes_existing(tmp_path: Path) -> None:
    game = tmp_path / "nwn"
    _write(game / "nwn.ini", "a\n")  # settings.tml intentionally absent
    snap = snapshot(game)
    assert set(snap) == {"nwn.ini"}
