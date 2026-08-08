"""The start-up sound: finding it, and choosing not to play it.

The preference existed, was shown in two settings screens, saved and reloaded —
and read by nothing. These cover the part that has judgement in it: where the
game keeps the file, and every reason not to make a noise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vaultkeeper.game.startup_sound import default_sound, resolve_sound


def _game(tmp_path: Path, *parts: str) -> Path:
    """A game root with the autorun sound at ``parts``."""
    root = tmp_path / "NWN"
    sound = root.joinpath(*parts)
    sound.parent.mkdir(parents=True, exist_ok=True)
    sound.write_bytes(b"RIFF....WAVE")
    return root


class TestFindingIt:
    def test_the_enhanced_edition_layout(self, tmp_path):
        """Where a real EE install keeps it: <game>/data/mus/mus_autorun.wav."""
        root = _game(tmp_path, "data", "mus", "mus_autorun.wav")
        assert default_sound(root) == root / "data" / "mus" / "mus_autorun.wav"

    def test_the_classic_layout(self, tmp_path):
        root = _game(tmp_path, "music", "mus_autorun.wav")
        assert default_sound(root) == root / "music" / "mus_autorun.wav"

    def test_a_game_without_one(self, tmp_path):
        (tmp_path / "NWN").mkdir()
        assert default_sound(tmp_path / "NWN") is None

    def test_no_game_at_all(self):
        assert default_sound(None) is None
        assert default_sound("") is None

    def test_a_missing_folder_is_not_an_error(self, tmp_path):
        assert default_sound(tmp_path / "nowhere") is None


class TestChoosingIt:
    def test_a_configured_file_wins(self, tmp_path):
        root = _game(tmp_path, "data", "mus", "mus_autorun.wav")
        mine = tmp_path / "mine.wav"
        mine.write_bytes(b"RIFF")
        assert resolve_sound(str(mine), root) == mine

    def test_a_configured_file_that_has_gone_falls_back_to_the_game(self, tmp_path):
        """An uninstalled sound pack should not quietly turn the setting off."""
        root = _game(tmp_path, "data", "mus", "mus_autorun.wav")
        assert resolve_sound(str(tmp_path / "deleted.wav"), root) == (
            root / "data" / "mus" / "mus_autorun.wav"
        )

    def test_nothing_configured_and_nothing_shipped(self, tmp_path):
        (tmp_path / "NWN").mkdir()
        assert resolve_sound("", tmp_path / "NWN") is None


# -- the decision to play at all ------------------------------------------------ #
class _Settings:
    def __init__(self, on: bool, path: str = ""):
        self.startup_sound = on
        self.startup_sound_path = path


def test_the_setting_off_means_nothing_is_even_loaded(qtbot, monkeypatch):
    from vaultkeeper.ui import app as app_module

    monkeypatch.setattr(
        app_module, "logger", app_module.logger
    )  # keep the real logger; assert on the return
    assert app_module._play_startup_sound(_Settings(False), None) is None


def test_holding_ctrl_suppresses_it(qtbot, monkeypatch):
    """VB's escape hatch, for when the fanfare is the last thing you want."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    from vaultkeeper.ui import app as app_module

    monkeypatch.setattr(
        QGuiApplication, "queryKeyboardModifiers", lambda: Qt.KeyboardModifier.ControlModifier
    )
    assert app_module._play_startup_sound(_Settings(True), None) is None


def test_no_sound_file_is_not_an_error(qtbot, tmp_path):
    from vaultkeeper.ui import app as app_module

    assert app_module._play_startup_sound(_Settings(True, ""), None) is None


def test_it_plays_and_the_player_is_handed_back_to_be_kept_alive(qtbot, tmp_path):
    """QSoundEffect stops the instant it is collected, so the caller must hold it."""
    from vaultkeeper.ui import app as app_module

    root = _game(tmp_path, "data", "mus", "mus_autorun.wav")

    class Ctx:
        game_root = root

    class Controller:
        ctx = Ctx()

    effect = app_module._play_startup_sound(_Settings(True), Controller())
    if effect is None:
        pytest.skip("no QtMultimedia or no audio device on this runner")
    assert effect.source().fileName() == "mus_autorun.wav"


def test_a_broken_audio_stack_never_stops_the_app(qtbot, monkeypatch):
    from vaultkeeper.ui import app as app_module

    def explode():
        raise RuntimeError("no audio device")

    monkeypatch.setattr(
        "PySide6.QtGui.QGuiApplication.queryKeyboardModifiers", lambda: explode()
    )
    assert app_module._play_startup_sound(_Settings(True), None) is None
