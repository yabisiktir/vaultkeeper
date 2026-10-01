"""A save's screen image on hover (VB ImageToolTip / BehaviourScreenTip / ConfigSaveScreenCrop)."""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QLabel

from vaultkeeper.ui.screen_tip import ScreenTip, crop_values, parse_crop, screen_pixmap


def _write_tga(path: Path, w: int = 8, h: int = 20) -> Path:
    """A tiny uncompressed 24-bit TGA the reader can decode."""
    header = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 24, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + bytes([0, 0, 255] * (w * h)))
    return path


# -- the crop setting (VB ValidateScreenCrop) --------------------------------- #
def test_crop_text_is_top_comma_bottom() -> None:
    assert parse_crop("24, 88") == (24, 88)
    assert parse_crop(" 0,0 ") == (0, 0)
    assert parse_crop("206, 206") == (206, 206)


def test_invalid_crop_text_is_refused_and_the_default_used() -> None:
    for text in ("", "24", "24, 88, 3", "a, b", "-1, 5", "207, 0"):
        assert parse_crop(text) is None, text
        assert crop_values(text) == (24, 88)


def test_the_image_is_cropped_top_and_bottom(qtbot, tmp_path) -> None:
    pixmap = screen_pixmap(_write_tga(tmp_path / "screen.tga", 8, 20), (3, 5))
    assert (pixmap.width(), pixmap.height()) == (8, 12)


def test_a_crop_larger_than_the_image_leaves_it_whole(qtbot, tmp_path) -> None:
    pixmap = screen_pixmap(_write_tga(tmp_path / "screen.tga", 8, 20), (15, 15))
    assert pixmap.height() == 20


def test_no_file_no_image(qtbot, tmp_path) -> None:
    assert screen_pixmap(tmp_path / "missing.tga") is None


# -- the hover itself --------------------------------------------------------- #
def test_hover_shows_the_image_instead_of_the_tooltip(qtbot, tmp_path) -> None:
    screen = _write_tga(tmp_path / "screen.tga")
    label = QLabel("Game Saves")
    qtbot.addWidget(label)
    tip = ScreenTip(label, lambda _pos: screen, crop=lambda: "2, 2")
    assert tip.show_at(QPoint(1, 1), QPoint(10, 10))
    assert tip.popup.isVisible()
    assert tip.popup.pixmap().height() == 16
    tip.hide()
    assert not tip.popup.isVisible()


def test_hover_does_nothing_when_the_setting_is_off(qtbot, tmp_path) -> None:
    screen = _write_tga(tmp_path / "screen.tga")
    label = QLabel("Game Saves")
    qtbot.addWidget(label)
    tip = ScreenTip(label, lambda _pos: screen, enabled=lambda: False)
    assert not tip.show_at(QPoint(1, 1), QPoint(10, 10))
    assert not tip.popup.isVisible()


def test_hover_with_no_save_keeps_the_ordinary_tooltip(qtbot) -> None:
    label = QLabel("Game Saves")
    qtbot.addWidget(label)
    tip = ScreenTip(label, lambda _pos: None)
    assert not tip.show_at(QPoint(1, 1), QPoint(10, 10))


# -- where NIT shows it ------------------------------------------------------- #
def _saves_controller(tmp_path):
    from tests.test_game_saves_manager import _controller

    controller = _controller(tmp_path)
    saves = tmp_path / "gameuser" / "saves"
    _write_tga(saves / "000002 - camp" / "screen.tga")
    return controller, saves


def test_the_latest_save_screen_is_the_newest_save(tmp_path) -> None:
    """VB NwGs.CurrentInfo: the save the Game Saves button pictures."""
    import os

    controller, saves = _saves_controller(tmp_path)
    os.utime(saves / "000002 - camp" / "Adventure.sav", (2_000_000_000, 2_000_000_000))
    controller._play_loop = None
    assert controller.latest_save_screen() == saves / "000002 - camp" / "screen.tga"


def test_the_game_saves_ribbon_button_has_the_screen_tip(qtbot, tmp_path) -> None:
    from vaultkeeper.config.settings import load_settings, save_settings
    from vaultkeeper.ui.main_window import MainWindow

    controller, saves = _saves_controller(tmp_path)
    window = MainWindow(controller)
    qtbot.addWidget(window)
    tip = window.game_saves_screen_tip
    controller.latest_save_screen = lambda: saves / "000002 - camp" / "screen.tga"
    assert tip.show_at(QPoint(1, 1), QPoint(10, 10))
    tip.hide()

    settings = load_settings()
    settings.screen_tip = False  # BehaviourScreenTip off
    save_settings(settings)
    assert not tip.show_at(QPoint(1, 1), QPoint(10, 10))


def test_the_manager_shows_it_over_a_saves_location(qtbot, tmp_path) -> None:
    from vaultkeeper.ui.dialogs.game_saves_manager import GameSavesManager

    controller, saves = _saves_controller(tmp_path)
    dlg = GameSavesManager.show_for(controller)
    qtbot.addWidget(dlg)
    dlg.show()
    rows = {dlg.table.topLevelItem(i).text(0): dlg.table.topLevelItem(i)
            for i in range(dlg.table.topLevelItemCount())}
    header = dlg.table.header()
    for name, expected in (("000002 - camp", True), ("000000 - quicksave", False)):
        rect = dlg.table.visualItemRect(rows[name])
        location = QPoint(header.sectionViewportPosition(2) + 2, rect.center().y())
        found = dlg._screen_at(location)
        assert (found == saves / name / "screen.tga") is expected
        if expected:  # but not over the other columns
            folder = QPoint(header.sectionViewportPosition(0) + 2, rect.center().y())
            assert dlg._screen_at(folder) is None


def test_the_character_summary_shows_it_when_enabled(qtbot, tmp_path) -> None:
    from tests.test_character_viewer import _char
    from vaultkeeper.ui.dialogs.character_viewer import CharacterViewer

    save = tmp_path / "000002 - camp"
    screen = _write_tga(save / "screen.tga")
    cf = _char("Hero", save / "player.bic")
    off = CharacterViewer([cf], None)
    qtbot.addWidget(off)
    assert not hasattr(off, "screen_tip")  # BehaviourScreenTipChar is off by default

    on = CharacterViewer([cf], None, save_screen_tips=True, screen_crop="0, 0")
    qtbot.addWidget(on)
    on._list.setCurrentRow(0)
    assert on._save_screen() == screen
    assert on.screen_tip.show_at(QPoint(1, 1), QPoint(10, 10))
    on.screen_tip.hide()


def test_settings_carry_nits_three_preferences(qtbot) -> None:
    from vaultkeeper.config.settings import Settings
    from vaultkeeper.ui.dialogs.settings_dialog import SettingsDialog

    defaults = Settings()
    assert (defaults.screen_tip, defaults.screen_tip_character, defaults.save_screen_crop) == (
        True, False, "24, 88"
    )
    dlg = SettingsDialog(defaults)
    qtbot.addWidget(dlg)
    dlg.screen_tip.setChecked(False)
    dlg.screen_tip_character.setChecked(True)
    dlg.save_screen_crop.setText("10,20")
    settings = Settings()
    dlg.apply_to(settings)
    assert (settings.screen_tip, settings.screen_tip_character, settings.save_screen_crop) == (
        False, True, "10, 20"
    )
    dlg.save_screen_crop.setText("999,1")  # invalid: the old value stays
    dlg.apply_to(settings)
    assert settings.save_screen_crop == "10, 20"
