"""NIT's Run/Web menu item editor (VB MenuItemEditor), owner decision 2026-09-28."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication

from vaultkeeper.ui.dialogs.menu_item_editor import MAX_CHARACTERS, MenuItemEditor


def test_run_item_needs_an_existing_program_and_names_itself(qtbot, tmp_path):
    program = tmp_path / "nwnexplorer.exe"
    program.write_bytes(b"MZ")
    dlg = MenuItemEditor("run")
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "Create Run Menu Item"
    assert not dlg.save_button.isEnabled()

    dlg.location.setText(str(tmp_path / "missing.exe"))
    assert not dlg.save_button.isEnabled()
    dlg.location.setText(str(program))
    assert dlg.item_text == "Nwnexplorer", "NIT fills the text from the file name"
    assert dlg.save_button.isEnabled()


def test_menu_text_is_limited_counted_and_unique(qtbot, tmp_path):
    program = tmp_path / "leto.exe"
    program.write_bytes(b"MZ")
    dlg = MenuItemEditor("run", text="Leto", location=str(program), other_texts=["&Toolset"])
    qtbot.addWidget(dlg)
    assert dlg.windowTitle() == "Update Run Menu Item"
    assert dlg.char_count.format() == f"4 out of {MAX_CHARACTERS} characters used."

    dlg.menu_text.setText("x" * 50)
    assert len(dlg.item_text) == MAX_CHARACTERS

    dlg.menu_text.setText("Toolset")
    assert dlg.status.text() == "Menu Text has already been used."
    assert not dlg.save_button.isEnabled()


def test_a_new_web_item_starts_from_a_url_on_the_clipboard(qtbot):
    QGuiApplication.clipboard().setText("https://neverwintervault.org/project/nwn1/x")
    dlg = MenuItemEditor("web")
    qtbot.addWidget(dlg)
    assert dlg.item_location == "https://neverwintervault.org/project/nwn1/x"

    QGuiApplication.clipboard().setText("not a url")
    plain = MenuItemEditor("web")
    qtbot.addWidget(plain)
    assert plain.item_location == ""


def test_save_checks_the_web_page_answers(qtbot):
    QGuiApplication.clipboard().setText("")
    dlg = MenuItemEditor("web", page_exists=lambda _url: False)
    qtbot.addWidget(dlg)
    dlg.menu_text.setText("Vault")
    dlg.location.setText("https://gone.example/")
    assert dlg.save_button.isEnabled()

    dlg.save_button.click()

    assert dlg.result() == 0, "stays open"
    assert dlg.status.text() == "The web address (URL) you specified cannot be opened"
    assert not dlg.save_button.isEnabled()

    ok = MenuItemEditor("web", page_exists=lambda _url: True)
    qtbot.addWidget(ok)
    ok.menu_text.setText("Vault")
    ok.location.setText("https://neverwintervault.org/")
    ok.save_button.click()
    assert ok.result() == 1
