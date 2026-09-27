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


# -- NIT's RichTextToolbar (screen parity) ------------------------------------ #
def test_the_bar_leads_with_nits_buttons_in_nits_order(qtbot, tmp_path) -> None:
    """LazWorks RichTextToolbar: WordPad | cut..paste as text | B I U S colour |
    undo redo | select all, find. Vaultkeeper's extras come after them."""
    win, _c = _window(qtbot, tmp_path)
    texts = [a.text() for a in win._notes_bar.actions() if a.text()][:14]
    assert texts == [
        "Open with your text editor", "Cut", "Copy", "Paste", "Paste as Text",
        "Bold", "Italic", "Underline", "Strike-through", "Font Colour…",
        "Undo", "Redo", "Select All", "Find",
    ]
    assert all(not a.icon().isNull() for a in win._notes_bar.actions()[:5] if a.text())


def test_paste_as_text_drops_the_clipboards_formatting(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtCore import QMimeData
    from PySide6.QtGui import QGuiApplication

    win, _c = _window(qtbot, tmp_path)
    monkeypatch.setattr(win, "_confirm_save_notes", lambda _m: True)
    mime = QMimeData()
    mime.setHtml("<b>loud</b>")
    mime.setText("loud")
    QGuiApplication.clipboard().setMimeData(mime)
    win._details.moveCursor(QTextCursor.MoveOperation.End)
    next(a for a in win._notes_bar.actions() if a.text() == "Paste as Text").trigger()

    assert win._details.toPlainText().endswith("loud")
    assert not win._details.currentCharFormat().fontWeight() > 400


def test_open_with_text_editor_saves_then_opens_the_notes_file(
    qtbot, tmp_path, monkeypatch
) -> None:
    from PySide6.QtGui import QDesktopServices

    win, c = _window(qtbot, tmp_path)
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    win._details.moveCursor(QTextCursor.MoveOperation.End)
    win._details.insertPlainText(" Edited.")

    win._notes_bar.open_external.trigger()

    assert [u.toLocalFile() for u in opened] == [str(c.mod_notes_path("Noted"))]
    assert "Edited." in "".join(p.text for p in c.read_notes_document("Noted"))
    assert not win._details.document().isModified()


def test_empty_notes_still_get_a_file_to_open(tmp_path) -> None:
    c = ProfileController.open_profile(
        profile_mods_dir=tmp_path / "Profiles" / "P",
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )
    path = c.notes_file_for_editing("Blank", [])
    assert path.is_file() and path.read_text().startswith("{\\rtf1")
