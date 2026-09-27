"""The notes pane keeps NIT's formatting (logic audit 3i N4, owner decision 2026-09-27)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QTextCursor

from vaultkeeper.core.rich_rtf import Paragraph, Style
from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.main_window import MainWindow

NIT_NOTE = (
    "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0\\fnil Segoe UI;}}"
    "{\\colortbl ;\\red200\\green0\\blue0;}"
    "\\pard Plain \\b bold\\b0  and \\cf1 red\\cf0 .\\par}"
)


def _window(qtbot, tmp_path: Path) -> tuple[MainWindow, ProfileController]:
    profile_mods = tmp_path / "Profiles" / "P"
    profile_mods.mkdir(parents=True)
    c = ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    c.create_mod("Noted")
    path = c.mod_notes_path("Noted")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(NIT_NOTE)
    win = MainWindow(c)
    qtbot.addWidget(win)
    win._select_mod_by_name("Noted")
    return win, c


def _styles(c: ProfileController) -> dict[str, Style]:
    (para,) = c.read_notes_document("Noted")
    return dict(para.runs)


def test_a_formatted_note_survives_an_edit(qtbot, tmp_path, monkeypatch) -> None:
    win, c = _window(qtbot, tmp_path)
    assert win._details.toPlainText() == "Plain bold and red."
    monkeypatch.setattr(win, "_confirm_save_notes", lambda _m: True)

    cursor = win._details.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" More.")
    win._save_current_notes()

    styles = _styles(c)
    assert styles["bold"].bold
    assert styles["red"].color == (200, 0, 0)
    assert "More." in "".join(styles)


def test_the_bold_button_formats_the_selection(qtbot, tmp_path, monkeypatch) -> None:
    win, c = _window(qtbot, tmp_path)
    monkeypatch.setattr(win, "_confirm_save_notes", lambda _m: True)
    cursor = win._details.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)  # "Plain"
    win._details.setTextCursor(cursor)

    win._notes_bar.bold.trigger()
    win._save_current_notes()

    assert _styles(c)["Plain"].bold


def test_plain_notes_still_save_as_plain_text(qtbot, tmp_path) -> None:
    _win, c = _window(qtbot, tmp_path)
    c.save_notes_document("Noted", [Paragraph([("just text", Style())])])
    assert c.read_notes("Noted") == "just text"
