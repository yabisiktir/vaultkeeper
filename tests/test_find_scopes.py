"""Find is one command with three meanings, chosen by focus (VB findoperations).

"The scope of the search operation depends on which element in the UI has
focus." Before this, Find always opened the profile search, which made the
other two scopes unreachable from the menu they are documented under.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from vaultkeeper.ui.controller import ProfileController
from vaultkeeper.ui.dialogs.find_text import FindTextDialog
from vaultkeeper.ui.main_window import MainWindow


@pytest.fixture()
def controller(tmp_path: Path) -> ProfileController:
    profile_mods = tmp_path / "Profiles" / "P"
    for name in ("Alpha", "Beta"):
        (profile_mods / name / ".Mod Installer" / "hak").mkdir(parents=True)
        (profile_mods / name / ".Mod Installer" / "hak" / f"{name}.hak").write_bytes(b"X")
    return ProfileController.open_profile(
        profile_mods_dir=profile_mods,
        game_root=tmp_path / "NWN",
        store_path=tmp_path / "Data" / "P.json",
    )


def _find_target(win: MainWindow):
    """What Find opened, as a (kind, widget) pair."""
    win._on_find()
    dialog = getattr(win, "_find_text_dialog", None)
    if dialog is not None and dialog.isVisible():
        return "text", dialog._target
    return "profile", getattr(win, "_find_dialog", None)


def test_focus_on_the_mod_list_searches_the_whole_profile(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win._tree.setFocus()

    kind, target = _find_target(win)
    assert kind == "profile" and target is not None


def test_focus_in_the_notes_searches_the_text(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.show()
    win._details.setFocus()

    kind, target = _find_target(win)
    assert kind == "text" and target is win._details


def test_focus_in_the_contents_list_steps_through_its_rows(qtbot, controller):
    win = MainWindow(controller)
    qtbot.addWidget(win)
    win.show()
    win._contents.setFocus()

    kind, target = _find_target(win)
    assert kind == "text" and target is win._contents


# -- The dialog itself --------------------------------------------------------- #
def test_stepping_through_occurrences_in_text(qtbot):
    from PySide6.QtWidgets import QTextEdit

    editor = QTextEdit()
    editor.setPlainText("one hak\ntwo hak\nthree")
    dialog = FindTextDialog(editor)
    qtbot.addWidget(dialog)
    dialog.text.setText("hak")

    assert dialog.find_next() is True
    first = editor.textCursor().position()
    assert dialog.find_next() is True
    assert editor.textCursor().position() > first
    # Wrapping around is not "no more occurrences" — there plainly are some.
    assert dialog.find_next() is True
    assert dialog.message.text() == ""


def test_text_that_is_not_there_says_so(qtbot):
    from PySide6.QtWidgets import QTextEdit

    editor = QTextEdit()
    editor.setPlainText("one two three")
    dialog = FindTextDialog(editor)
    qtbot.addWidget(dialog)
    dialog.text.setText("nowhere")

    assert dialog.find_next() is False
    assert "no more occurrences" in dialog.message.text()


def test_stepping_through_rows_in_a_list(qtbot):
    tree = QTreeWidget()
    tree.setHeaderLabels(["File"])
    for name in ("alpha.hak", "beta.tlk", "gamma.hak"):
        tree.addTopLevelItem(QTreeWidgetItem([name]))
    dialog = FindTextDialog(tree)
    qtbot.addWidget(dialog)
    dialog.text.setText("hak")

    assert dialog.find_next() is True
    assert tree.currentItem().text(0) == "alpha.hak"
    assert dialog.find_next() is True
    assert tree.currentItem().text(0) == "gamma.hak"
    # Previous walks back the other way, as the help says it does.
    assert dialog.find_previous() is True
    assert tree.currentItem().text(0) == "alpha.hak"


def test_list_search_is_case_insensitive_unless_asked(qtbot):
    tree = QTreeWidget()
    tree.setHeaderLabels(["File"])
    tree.addTopLevelItem(QTreeWidgetItem(["Alpha.HAK"]))
    dialog = FindTextDialog(tree)
    qtbot.addWidget(dialog)
    dialog.text.setText("hak")

    assert dialog.find_next() is True
    dialog.match_case.setChecked(True)
    assert dialog.find_next() is False


def test_the_file_viewer_can_be_searched(qtbot, tmp_path):
    """findtext.htm documents a Find button on the viewer itself."""
    from vaultkeeper.ui.dialogs.text_viewer import TextViewer

    log = tmp_path / "nit.log"
    log.write_text("start\nfailed to install\nend\n")
    viewer = TextViewer(log, "NIT Log File")
    qtbot.addWidget(viewer)

    viewer.open_find()
    viewer.find_dialog.text.setText("failed")
    assert viewer.find_dialog.find_next() is True
    assert "failed" in viewer.editor.textCursor().selectedText()
